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
    return sum(int(scores.get(c["id"], 0)) * int(c["weight"]) for c in criteria)


def has_auto_reject(scores: dict[str, int], criteria: Iterable[dict]) -> bool:
    """True if any criterion flagged ``auto_reject_on_zero`` scored 0."""
    return any(
        int(scores.get(c["id"], 0)) == 0
        for c in criteria
        if c.get("auto_reject_on_zero")
    )


def missing_criteria(scores: dict[str, int], criteria: Iterable[dict]) -> list[str]:
    """Return criterion IDs that have not been scored yet."""
    return [c["id"] for c in criteria if c["id"] not in scores]


def max_weighted_total(criteria: Iterable[dict]) -> int:
    """The maximum achievable weighted total for a given set of criteria."""
    return sum(int(c["weight"]) * int(c["max"]) for c in criteria)
