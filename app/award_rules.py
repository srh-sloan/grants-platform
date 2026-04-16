"""Award-size and tier rules -- pure helpers, no I/O.

**Stream ownership:** Assessor & scoring (Stream C).

Reads ``grant.config_json["award_rules"]`` (optional block). If absent, falls
back to the flat ``award_ranges`` block for simple min/max bounds.

Award rules contract (add to seed/grants/<slug>.json)::

    "award_rules": [
        {
            "id": "sustainability_tier",
            "label": "Sustainability tier",
            "description": "Projects scoring 3 on sustainability are eligible for the higher capital tier.",
            "criterion_id": "outcomes",
            "criterion_threshold": 2,
            "operator": "gte",
            "award_type": "capital",
            "award_min": 100000,
            "award_max": 200000
        },
        {
            "id": "standard_tier",
            "label": "Standard tier",
            "description": "Projects below the sustainability threshold receive the standard award range.",
            "criterion_id": "outcomes",
            "criterion_threshold": 2,
            "operator": "lt",
            "award_type": "revenue",
            "award_min": 50000,
            "award_max": 100000
        }
    ]

Operators: ``gte`` (>=), ``gt`` (>), ``lte`` (<=), ``lt`` (<), ``eq`` (==).

If no ``award_rules`` block exists, :func:`derive_award_range` returns the flat
``award_ranges`` min/max from the grant config (unchanged behaviour).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AwardRange:
    """The applicable award range for a scored application."""

    award_type: str           # "revenue", "capital", or "both"
    award_min: int            # minimum award amount in GBP
    award_max: int            # maximum award amount in GBP
    rule_id: str | None       # which rule matched, or None for flat fallback
    rule_label: str | None    # human-readable label for the matched rule


def _check_operator(score: int, operator: str, threshold: int) -> bool:
    ops = {
        "gte": score >= threshold,
        "gt": score > threshold,
        "lte": score <= threshold,
        "lt": score < threshold,
        "eq": score == threshold,
    }
    return ops.get(operator, False)


def derive_award_range(
    scores: dict[str, int],
    grant_config: dict,
) -> AwardRange | None:
    """Return the applicable award range for a given set of criterion scores.

    Evaluates ``award_rules`` in order and returns the first matching rule.
    Falls back to the flat ``award_ranges`` block if no rules are defined.
    Returns None if neither block is present.
    """
    rules = grant_config.get("award_rules") or []

    for rule in rules:
        cid = rule.get("criterion_id")
        threshold = int(rule.get("criterion_threshold", 0))
        operator = rule.get("operator", "gte")
        score = scores.get(cid, 0) if cid else 0

        if _check_operator(score, operator, threshold):
            return AwardRange(
                award_type=rule.get("award_type", "revenue"),
                award_min=int(rule.get("award_min", 0)),
                award_max=int(rule.get("award_max", 0)),
                rule_id=rule.get("id"),
                rule_label=rule.get("label"),
            )

    # Flat fallback
    flat = grant_config.get("award_ranges")
    if flat:
        return AwardRange(
            award_type="revenue",
            award_min=int(flat.get("revenue_min", 0)),
            award_max=int(flat.get("revenue_max", 0)),
            rule_id=None,
            rule_label="Standard award range",
        )

    return None


def check_scale_up_eligibility(
    scores: dict[str, int],
    grant_config: dict,
) -> tuple[bool, str]:
    """Check whether the application meets the conditional scale-up clause.

    Reads ``grant.config_json["scale_up_clause"]`` (optional). Returns
    ``(eligible, reason)`` where reason is a human-readable explanation.

    Scale-up clause contract::

        "scale_up_clause": {
            "description": "Projects that score 3 on all deliverability criteria may apply for a scale-up award.",
            "criteria": ["deliverability1", "deliverability2"],
            "min_score": 3,
            "scale_up_max": 300000
        }
    """
    clause = grant_config.get("scale_up_clause")
    if not clause:
        return False, "No scale-up clause defined for this grant."

    criteria_ids: list[str] = clause.get("criteria", [])
    min_score: int = int(clause.get("min_score", 3))
    failing = [
        cid for cid in criteria_ids
        if scores.get(cid, 0) < min_score
    ]

    if not failing:
        scale_max = clause.get("scale_up_max", 0)
        return True, "Eligible for scale-up award (max £{:,}).".format(scale_max)

    return False, "Does not meet scale-up threshold on: {}.".format(", ".join(failing))
