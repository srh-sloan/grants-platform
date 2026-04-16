"""
assessor_ai.py — AI assessment layer for EHCF grant applications.

Usage:
    from assessor_ai import assess_application
    assessment = assess_application(application_id)

Place this file at app/assessor_ai.py. Requires ANTHROPIC_API_KEY in env.
The Assessment model must have a gap_analysis (JSON) and auto_rejected (bool) column
in addition to the fields defined in CLAUDE.md.
"""

import json
import logging
import os
from datetime import datetime, timezone

import anthropic

from app.models import Assessment, ApplicationSection, db
from scoring import WEIGHTS, calculate_weighted_score, has_auto_reject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (out of 300)
# All-2s = 200, all-3s = 300. Fund bar set above all-2s to require some 3s.
# ---------------------------------------------------------------------------
FUND_THRESHOLD = 210   # >= 210 → fund
REFER_THRESHOLD = 150  # >= 150 → refer, < 150 → reject

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_RUBRIC = """\
Score each criterion on a scale of 0–3:
  0 = Unacceptable — fails to address the requirement; triggers automatic rejection
  1 = Satisfactory — meets the minimum threshold but lacks depth or evidence
  2 = Good — solid response with evidence but identifiable gaps remain
  3 = Excellent — comprehensive, well-evidenced, clearly exceeds expectations

Criterion-specific guidance:
  skills          — Does the organisation demonstrate relevant expertise, track record,
                    and staffing capacity to deliver the proposed project?
  proposal1       — Is the homelessness problem clearly defined with credible local data
                    and evidence of need in the target area?
  proposal2       — Is the proposed project clearly described, realistic in scope,
                    and appropriate to the identified need?
  deliverability1 — Are milestones realistic, governance arrangements sound, and
                    organisational delivery capacity demonstrated?
  deliverability2 — Are key risks clearly identified with credible, proportionate
                    mitigation measures?
  cost            — Is the budget detailed, proportionate, justified, and does it
                    represent value for money for public funds?
  outcomes        — Are outcomes measurable, directly relevant to reducing homelessness,
                    and achievable within the grant period?
"""

_SYSTEM_PROMPT = f"""\
You are an expert grant assessor for the Ending Homelessness in Communities Fund (EHCF),
a £37 million MHCLG programme funding voluntary, community, and faith sector organisations
to reduce homelessness across England.

Your task is to score a grant application objectively against the seven EHCF assessment criteria.

{_RUBRIC}

You must respond with valid JSON only. Do not include prose, markdown, or code fences.
Your response must match this exact structure — all fields are required:

{{
  "scores": {{
    "skills":          <integer 0–3>,
    "proposal1":       <integer 0–3>,
    "proposal2":       <integer 0–3>,
    "deliverability1": <integer 0–3>,
    "deliverability2": <integer 0–3>,
    "cost":            <integer 0–3>,
    "outcomes":        <integer 0–3>
  }},
  "notes": "<3-sentence plain English briefing for a human assessor: sentence 1 = the strongest aspects of this application, sentence 2 = the most significant weaknesses, sentence 3 = what specifically needs human attention or verification>",
  "gap_analysis": {{
    "skills":          "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>",
    "proposal1":       "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>",
    "proposal2":       "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>",
    "deliverability1": "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>",
    "deliverability2": "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>",
    "cost":            "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>",
    "outcomes":        "<one sentence stating what is specifically missing to reach a 3, or null if score is already 3>"
  }}
}}
"""


def _build_application_text(section: ApplicationSection) -> str:
    """Render all application sections as structured text for the prompt."""
    field_map = [
        ("Skills and Experience", section.skills_and_experience),
        ("Proposal Part 1 — Challenges and Local Evidence", section.proposal_part1),
        ("Proposal Part 2 — Project Description", section.proposal_part2),
        ("Deliverability Part 1 — Milestones and Governance", section.deliverability_part1),
        ("Deliverability Part 2 — Risk Register", section.deliverability_part2),
        ("Cost and Value for Money", section.cost_and_value),
        ("Outcomes and Impact", section.outcomes_and_impact),
    ]
    parts = []
    for label, content in field_map:
        if isinstance(content, dict):
            text = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            text = str(content) if content else "(not provided)"
        parts.append(f"## {label}\n{text}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def _call_claude(application_text: str) -> dict:
    """
    Call Claude and return the parsed JSON response dict.
    Raises ValueError if the response cannot be parsed.
    Raises anthropic.APIError (and subclasses) on API failures.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Score the following EHCF grant application against the seven criteria. "
                    "Return valid JSON only.\n\n"
                    + application_text
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown code fences if Claude adds them despite instructions
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Claude returned non-JSON response (first 500 chars): %s", raw[:500])
        raise ValueError(f"Claude response was not valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_scores(scores: dict) -> dict:
    """
    Ensure all 7 criterion keys are present and values are integers 0–3.
    Returns a clean, typed dict.
    """
    expected = set(WEIGHTS.keys())
    missing = expected - set(scores.keys())
    if missing:
        raise ValueError(f"Claude scores dict is missing keys: {sorted(missing)}")

    clean = {}
    for key in expected:
        try:
            val = int(scores[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Score for '{key}' is not an integer: {scores[key]!r}") from exc
        if val < 0 or val > 3:
            raise ValueError(f"Score for '{key}' is out of range (0–3): {val}")
        clean[key] = val
    return clean


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def assess_application(application_id: int) -> Assessment | None:
    """
    AI assessment of a submitted EHCF grant application.

    Reads all sections from application_sections for the given application_id,
    calls the Anthropic Claude API, then writes and returns an Assessment record.

    Returns None if no application_sections row exists for this application.
    Raises ValueError on unparseable Claude responses.
    Raises anthropic.APIError on API-level failures.

    NOTE: The Assessment model must include these columns beyond the CLAUDE.md spec:
      - gap_analysis  JSON  (per-criterion gap notes for scores < 3)
      - auto_rejected BOOL  (true if any criterion scored 0)
    """
    section = ApplicationSection.query.filter_by(application_id=application_id).first()
    if section is None:
        logger.error(
            "assess_application: no application_sections row found for application_id=%s",
            application_id,
        )
        return None

    application_text = _build_application_text(section)

    logger.info("assess_application: calling Claude for application_id=%s", application_id)
    parsed = _call_claude(application_text)

    scores = _validate_scores(parsed.get("scores", {}))
    notes = parsed.get("notes", "")
    raw_gap = parsed.get("gap_analysis", {})

    # Only retain gap analysis entries for criteria that did not score 3
    gap_analysis = {
        key: raw_gap.get(key)
        for key in WEIGHTS
        if scores[key] < 3 and raw_gap.get(key)
    }

    auto_rejected = has_auto_reject(scores)
    weighted_total = calculate_weighted_score(scores)

    if auto_rejected:
        recommendation = "reject"
    elif weighted_total >= FUND_THRESHOLD:
        recommendation = "fund"
    elif weighted_total >= REFER_THRESHOLD:
        recommendation = "refer"
    else:
        recommendation = "reject"

    assessment = Assessment(
        application_id=application_id,
        assessor_id=None,         # AI assessment; no human assessor assigned yet
        scores=scores,
        weighted_total=weighted_total,
        recommendation=recommendation,
        notes=notes,
        gap_analysis=gap_analysis,
        auto_rejected=auto_rejected,
        completed_at=datetime.now(timezone.utc),
    )
    db.session.add(assessment)
    db.session.commit()

    logger.info(
        "assess_application: application_id=%s | score=%s/300 | recommendation=%s | auto_rejected=%s",
        application_id,
        weighted_total,
        recommendation,
        auto_rejected,
    )

    return assessment
