"""Pure scoring helpers — no I/O, no Flask, no DB.

**Stream ownership:** Assessor & scoring (Stream C).

Every function here takes plain data in and returns plain data out. They are
safe to call from any blueprint, fixture, or script.

Contracts:

- ``scores``   — ``{criterion_id: int}``, e.g. ``{"skills": 2, "proposal2": 3}``.
- ``criteria`` — ``list[dict]`` taken straight from ``grant.config_json["criteria"]``.
  Each element has ``{"id", "label", "weight", "max", "auto_reject_on_zero"}``.
- Criterion weights must sum to 100 (enforced by :mod:`seed`); the maximum
  weighted total is therefore ``100 * max_raw_score`` (300 for a 0-3 scale).
"""

from __future__ import annotations

from collections.abc import Iterable


def calculate_weighted_score(scores: dict[str, int], criteria: Iterable[dict]) -> int:
    """Sum raw score × weight per criterion.

    Missing criteria in ``scores`` are treated as zero, so a partially-filled
    assessment still yields a number (useful for progress displays).
    """
    return sum(int(scores.get(c["id"]) or 0) * int(c["weight"]) for c in criteria)


def has_auto_reject(scores: dict[str, int], criteria: Iterable[dict]) -> bool:
    """True if any criterion flagged ``auto_reject_on_zero`` scored 0."""
    return any(
        int(scores.get(c["id"]) or 0) == 0
        for c in criteria
        if c.get("auto_reject_on_zero")
    )


def missing_criteria(scores: dict[str, int], criteria: Iterable[dict]) -> list[str]:
    """Return criterion IDs that have not been scored yet."""
    return [c["id"] for c in criteria if c["id"] not in scores]


def max_weighted_total(criteria: Iterable[dict]) -> int:
    """The maximum achievable weighted total for a given set of criteria."""
    return sum(int(c["weight"]) * int(c["max"]) for c in criteria)


# ---------------------------------------------------------------------------
# Multi-stage gate helpers
# ---------------------------------------------------------------------------


def eligibility_gate_status(scores_json: dict | None) -> bool | None:
    """Return the eligibility gate result, or None if not yet completed.

    The gate value is stored at ``scores_json["_eligibility_passed"]``.
    """
    if not scores_json:
        return None
    val = scores_json.get("_eligibility_passed")
    if val is None:
        return None
    return bool(val)


def declaration_gate_status(scores_json: dict | None) -> bool | None:
    """Return the declaration gate result, or None if not yet completed.

    The gate value is stored at ``scores_json["_declaration_passed"]``.
    """
    if not scores_json:
        return None
    val = scores_json.get("_declaration_passed")
    if val is None:
        return None
    return bool(val)


def all_criteria_scored(scores_json: dict | None, criteria: Iterable[dict]) -> bool:
    """True when every criterion in *criteria* has a score in *scores_json*."""
    if not scores_json:
        return False
    return all(c["id"] in scores_json for c in criteria)


def decision_allowed(
    scores_json: dict | None,
    criteria: list[dict],
) -> tuple[bool, str]:
    """Check whether the assessor may record a final decision.

    Returns ``(allowed, reason)``.  The decision is allowed when:
    - Eligibility gate is completed (pass *or* fail — a fail leads to reject).
    - If eligibility passed, all criteria must be scored *and* declaration
      must be passed.
    - If eligibility failed, the assessor can reject immediately.
    """
    elig = eligibility_gate_status(scores_json)
    if elig is None:
        return False, "Complete the eligibility check first."

    # Eligibility failed → immediate reject is allowed
    if elig is False:
        return True, ""

    # Eligibility passed → scoring + declaration required
    if not all_criteria_scored(scores_json, criteria):
        return False, "Score all criteria before recording a decision."

    decl = declaration_gate_status(scores_json)
    if decl is None:
        return False, "Complete the declaration before recording a decision."
    if decl is False:
        return False, "Declaration check failed — review and correct before recording a decision."

    return True, ""
