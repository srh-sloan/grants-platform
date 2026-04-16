"""AI-powered automatic assessment layer.

Queued from the applicant submission flow (:func:`queue_assessment`) and
processed on the shared background thread pool in :mod:`app.tasks`. Uses
Claude to:

  1. Read the applicant's answers and the grant's scoring criteria.
  2. Produce a score (0-max) for each criterion.
  3. Persist an Assessment row with scores_json, notes_json, weighted_total,
     and a recommendation.
  4. Send an email notification to the configured address.

Lifecycle of an AI-assessment row:

  queue_assessment()  → row PENDING
       │
       ▼
  _process_assessment() (background thread)
       │  row IN_PROGRESS, started_at set
       │
       ▼
  Claude call + JSON parse
       │
       ├── success → row COMPLETED, scores / notes / recommendation persisted
       └── failure → row FAILED, error_message stored, completed_at cleared

Retries: calling :func:`queue_assessment` on an existing FAILED row resets it
to PENDING and re-enqueues the work. COMPLETED and in-flight rows are treated
as idempotent no-ops.

Environment variables
---------------------
ANTHROPIC_API_KEY   Required. Claude API key.
NOTIFY_EMAIL        Recipient address for assessment notifications.
SMTP_HOST           SMTP server hostname (default: localhost).
SMTP_PORT           SMTP port (default: 587).
SMTP_USER           SMTP username (optional).
SMTP_PASSWORD       SMTP password (optional).
SMTP_FROM           Sender address (default: grants-platform@noreply.local).

The AI assessor user (assessor_id) is a synthetic system account upserted on
first run so the non-nullable FK is satisfied without a schema change.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import textwrap
from datetime import UTC, datetime
from email.mime.text import MIMEText

from app.extensions import db
from app.models import (
    Application,
    Assessment,
    AssessmentRecommendation,
    AssessmentStatus,
    User,
    UserRole,
)
from app.scoring import calculate_weighted_score, has_auto_reject

log = logging.getLogger(__name__)

_AI_ASSESSOR_EMAIL = "ai-assessor@system.local"
_MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# AI system user
# ---------------------------------------------------------------------------


def _get_or_create_ai_user() -> User:
    """Return the synthetic AI assessor user, creating it if absent."""
    user = User.query.filter_by(email=_AI_ASSESSOR_EMAIL).first()
    if user is None:
        user = User(
            email=_AI_ASSESSOR_EMAIL,
            password_hash="!",  # unusable password -- account cannot log in
            role=UserRole.ASSESSOR,
        )
        db.session.add(user)
        db.session.flush()
        log.info("Created synthetic AI assessor user (id=%s)", user.id)
    return user


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompt(application: Application, criteria: list[dict]) -> str:
    """Render a structured prompt for Claude from the application answers."""
    answers = application.answers_json or {}
    answers_block = "\n".join(
        "  {}: {}".format(key, json.dumps(value, ensure_ascii=False))
        for key, value in answers.items()
    ) or "  (no answers provided)"

    criteria_parts = []
    for c in criteria:
        header = "  - id={!r}, label={!r}, max={}, weight={}{}".format(
            c["id"],
            c["label"],
            c["max"],
            c["weight"],
            " [AUTO-REJECT if zero]" if c.get("auto_reject_on_zero") else "",
        )
        guidance = c.get("guidance", {})
        what = guidance.get("what_we_look_for", "")
        score_descs = guidance.get("scores", {})
        rubric_lines = []
        if what:
            rubric_lines.append("    What we look for: " + what)
        for score_val in sorted(score_descs.keys(), key=lambda x: int(x)):
            rubric_lines.append("    Score {}: {}".format(score_val, score_descs[score_val]))
        criteria_parts.append(header + ("\n" + "\n".join(rubric_lines) if rubric_lines else ""))
    criteria_block = "\n".join(criteria_parts)

    return (
        "You are an expert grant assessor for the {} programme.\n\n"
        "## Application answers\n{}\n\n"
        "## Scoring criteria\n"
        "Score each criterion from 0 to its stated max using the rubric below. "
        "Return ONLY valid JSON with no prose outside it.\n\n"
        "{}\n\n"
        "## Required JSON output (strictly this shape)\n"
        "{{\n"
        '  "scores": {{"<criterion_id>": <int>, ...}},\n'
        '  "notes": {{"<criterion_id>": "<rationale string citing specific evidence from the application>", ...}},\n'
        '  "gap_analysis": "<brief overall narrative of strengths and gaps>",\n'
        '  "recommendation": "fund" | "reject" | "refer"\n'
        "}}\n\n"
        "Apply the per-criterion rubric strictly. "
        "Auto-reject criteria must score > 0 unless the evidence is genuinely absent.\n"
        "Base the recommendation on the weighted total relative to max and any auto-reject flags."
    ).format(application.grant.name, answers_block, criteria_block)


def _parse_response(text: str) -> dict:
    """Extract the JSON block from Claude's response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------


def _send_notification(assessment: Assessment) -> None:
    """Email the assessment result to NOTIFY_EMAIL. Fails silently if unconfigured."""
    recipient = os.environ.get("NOTIFY_EMAIL", "")
    if not recipient:
        log.info("NOTIFY_EMAIL not configured — skipping notification")
        return
    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", "grants-platform@noreply.local")

    application = assessment.application
    org_name = application.organisation.name if application.organisation else "Unknown"
    grant_name = application.grant.name if application.grant else "Unknown"
    recommendation = (
        assessment.recommendation.value.upper() if assessment.recommendation else "N/A"
    )
    gap_analysis = assessment.notes_json.get("_gap_analysis", "No summary available.")

    score_lines = []
    criteria = application.grant.config_json.get("criteria", [])
    for c in criteria:
        cid = c["id"]
        score = assessment.scores_json.get(cid, "N/A")
        note = assessment.notes_json.get(cid, "")
        score_lines.append("  {}: {}/{}\n    {}".format(c["label"], score, c["max"], note))

    scores_block = "\n".join(score_lines) or "  No scores recorded."

    body = textwrap.dedent("""
        AI Assessment Complete

        Application ID : {}
        Organisation   : {}
        Grant          : {}
        Submitted      : {}

        Weighted total : {}
        Recommendation : {}

        --- Criterion Scores ---
        {}

        --- Overall Assessment ---
        {}

        Assessed at {} by AI (claude-sonnet-4-6).
        View application: /assess/{}
    """).strip().format(
        application.id,
        org_name,
        grant_name,
        application.submitted_at,
        assessment.weighted_total,
        recommendation,
        scores_block,
        gap_analysis,
        assessment.completed_at,
        application.id,
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "[{}] AI Assessment: {} -- {}".format(recommendation, org_name, grant_name)
    msg["From"] = smtp_from
    msg["To"] = recipient

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()

        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)

        server.sendmail(smtp_from, [recipient], msg.as_string())
        server.quit()
        log.info("Assessment notification sent to %s", recipient)
    except Exception as exc:
        log.warning("Failed to send assessment notification: %s", exc)


# ---------------------------------------------------------------------------
# API-key resolution
# ---------------------------------------------------------------------------


def _resolve_api_key() -> str | None:
    """Return the Anthropic API key, honouring a late-loaded .env as a fallback."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        return None
    return os.environ.get("ANTHROPIC_API_KEY")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def queue_assessment(application_id: int) -> Assessment | None:
    """Create (or revive) a PENDING Assessment row and enqueue AI processing.

    Returns the Assessment row immediately so the caller (submit handler,
    manual trigger route) can redirect the user to a page that shows the
    pending state. The actual Claude round-trip happens on the background
    thread pool in :mod:`app.tasks`; the row is updated in-place when it
    finishes.

    Semantics:

    * Missing application or grant without criteria → returns ``None``, no row
      created.
    * Missing ``ANTHROPIC_API_KEY`` → returns ``None``, no row created. This
      preserves the "silent no-op" shape that existing integration tests
      (``test_applicant.py``) rely on.
    * Existing COMPLETED row → idempotent no-op, returns the row unchanged.
    * Existing PENDING or IN_PROGRESS row → returns the row unchanged (a
      worker is already on it; we don't double-enqueue).
    * Existing FAILED row → reset to PENDING and re-enqueued. The retry button
      on the assessor detail page is the user-facing trigger for this path.
    """
    from flask import current_app

    application = db.session.get(Application, application_id)
    if application is None:
        log.warning("queue_assessment: application %s not found", application_id)
        return None

    criteria: list[dict] = application.grant.config_json.get("criteria", [])
    if not criteria:
        log.warning(
            "queue_assessment: grant %s has no criteria", application.grant.slug
        )
        return None

    if not _resolve_api_key():
        log.info("queue_assessment: ANTHROPIC_API_KEY not set — skipping queue")
        return None

    existing = Assessment.query.filter_by(application_id=application_id).first()
    if existing is not None:
        if existing.status == AssessmentStatus.FAILED:
            # Retry: reset the row and requeue. Keep the assessor_id and the
            # original primary key so any links the assessor has are stable.
            existing.status = AssessmentStatus.PENDING
            existing.started_at = None
            existing.completed_at = None
            existing.error_message = None
            existing.scores_json = {}
            existing.notes_json = {}
            existing.weighted_total = None
            existing.recommendation = None
            db.session.commit()
            assessment = existing
        else:
            log.info(
                "queue_assessment: application %s already has %s assessment",
                application_id,
                existing.status.value,
            )
            return existing
    else:
        ai_user = _get_or_create_ai_user()
        assessment = Assessment(
            application_id=application_id,
            assessor_id=ai_user.id,
            scores_json={},
            notes_json={},
            status=AssessmentStatus.PENDING,
        )
        db.session.add(assessment)
        db.session.commit()

    # Run on the background pool; in tests this runs inline (see app.tasks).
    from app.tasks import run_in_background

    run_in_background(
        current_app._get_current_object(),
        _process_assessment,
        application_id,
        assessment.id,
    )
    return assessment


def _process_assessment(application_id: int, assessment_id: int) -> None:
    """Worker entry point: perform the Claude call and update the row.

    Runs inside a background thread with an app context already pushed (see
    :func:`app.tasks.run_in_background`). Commits its own DB changes and never
    raises — any failure is stored on the row as :attr:`AssessmentStatus.FAILED`
    with a truncated ``error_message``.
    """
    assessment = db.session.get(Assessment, assessment_id)
    if assessment is None:
        log.error("_process_assessment: assessment %s missing", assessment_id)
        return

    assessment.status = AssessmentStatus.IN_PROGRESS
    assessment.started_at = datetime.now(UTC)
    db.session.commit()

    try:
        application = db.session.get(Application, application_id)
        if application is None:
            raise RuntimeError(f"application {application_id} not found")

        criteria: list[dict] = application.grant.config_json.get("criteria", [])
        if not criteria:
            raise RuntimeError("grant has no scoring criteria")

        api_key = _resolve_api_key()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic SDK not installed") from exc

        prompt = _build_prompt(application, criteria)
        client = anthropic.Anthropic(api_key=api_key)
        log.info(
            "_process_assessment: calling Claude for application %s", application_id
        )
        message = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        if not message.content:
            raise RuntimeError("empty response from Claude")
        raw = message.content[0].text

        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            log.error(
                "_process_assessment: failed to parse Claude response: %s\n%s",
                exc,
                raw,
            )
            raise RuntimeError("could not parse Claude response as JSON") from exc

        criteria_map = {c["id"]: c for c in criteria}
        scores: dict[str, int] = {}
        for k, v in parsed.get("scores", {}).items():
            if k in criteria_map:
                max_val = criteria_map[k].get("max", 3)
                scores[k] = max(0, min(int(v), max_val))
        notes: dict[str, str] = parsed.get("notes", {})
        gap_analysis: str = parsed.get("gap_analysis", "")
        raw_recommendation: str = parsed.get("recommendation", "refer")

        auto_rejected = has_auto_reject(scores, criteria)
        weighted_total = calculate_weighted_score(scores, criteria)

        if auto_rejected:
            recommendation = AssessmentRecommendation.REJECT
        else:
            try:
                recommendation = AssessmentRecommendation(raw_recommendation)
            except ValueError:
                recommendation = AssessmentRecommendation.REFER

        assessment.scores_json = scores
        assessment.notes_json = {**notes, "_gap_analysis": gap_analysis}
        assessment.weighted_total = weighted_total
        assessment.recommendation = recommendation
        assessment.completed_at = datetime.now(UTC)
        assessment.status = AssessmentStatus.COMPLETED
        assessment.error_message = None
        db.session.commit()

        log.info(
            "_process_assessment: application %s -> weighted_total=%s recommendation=%s",
            application_id,
            weighted_total,
            recommendation.value,
        )

        _send_notification(assessment)

    except Exception as exc:  # noqa: BLE001
        # Roll back any in-flight changes (notably the IN_PROGRESS commit is
        # already durable, but anything scheduled after it gets reverted) so
        # the FAILED update below lands cleanly.
        db.session.rollback()
        failed = db.session.get(Assessment, assessment_id)
        if failed is not None:
            failed.status = AssessmentStatus.FAILED
            failed.error_message = str(exc)[:500]
            failed.completed_at = datetime.now(UTC)
            db.session.commit()
        log.exception(
            "_process_assessment: application %s failed", application_id
        )


def assess_application(application_id: int) -> Assessment | None:
    """Synchronous wrapper around :func:`queue_assessment`.

    Kept for callers that want the old "run now, return the result" contract
    — the manual ``/run-ai`` trigger and existing tests. In production this
    still delegates to the background pool, so the caller returns as soon as
    the PENDING row is written. In tests (``TESTING=True``) the task runs
    inline and this function returns the fully-populated row (or ``None`` if
    parsing/API failed) to match the pre-async contract.
    """
    assessment = queue_assessment(application_id)
    if assessment is None:
        return None
    # In sync mode the worker has already finished; reload to pick up the
    # COMPLETED/FAILED state it wrote. In async mode this just returns the
    # PENDING row, which is fine for the UI code paths.
    db.session.refresh(assessment)
    if assessment.status == AssessmentStatus.FAILED:
        return None
    return assessment
