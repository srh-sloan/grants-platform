"""Tests for award-size and tier rules (app/award_rules.py)."""

from __future__ import annotations

import pytest

from app.award_rules import AwardRange, check_scale_up_eligibility, derive_award_range

GRANT_CONFIG_WITH_RULES = {
    "award_rules": [
        {
            "id": "high_tier",
            "label": "High sustainability tier",
            "criterion_id": "outcomes",
            "criterion_threshold": 3,
            "operator": "gte",
            "award_type": "capital",
            "award_min": 150000,
            "award_max": 200000,
        },
        {
            "id": "standard_tier",
            "label": "Standard tier",
            "criterion_id": "outcomes",
            "criterion_threshold": 3,
            "operator": "lt",
            "award_type": "revenue",
            "award_min": 50000,
            "award_max": 100000,
        },
    ],
    "award_ranges": {
        "revenue_min": 50000,
        "revenue_max": 200000,
    },
    "scale_up_clause": {
        "description": "Score 3 on both deliverability criteria for scale-up.",
        "criteria": ["deliverability1", "deliverability2"],
        "min_score": 3,
        "scale_up_max": 300000,
    },
}

GRANT_CONFIG_FLAT_ONLY = {
    "award_ranges": {
        "revenue_min": 50000,
        "revenue_max": 200000,
    }
}


# ---------------------------------------------------------------------------
# derive_award_range
# ---------------------------------------------------------------------------


def test_high_score_matches_high_tier():
    scores = {"outcomes": 3}
    result = derive_award_range(scores, GRANT_CONFIG_WITH_RULES)
    assert result is not None
    assert result.rule_id == "high_tier"
    assert result.award_type == "capital"
    assert result.award_min == 150000
    assert result.award_max == 200000


def test_low_score_matches_standard_tier():
    scores = {"outcomes": 2}
    result = derive_award_range(scores, GRANT_CONFIG_WITH_RULES)
    assert result is not None
    assert result.rule_id == "standard_tier"
    assert result.award_type == "revenue"
    assert result.award_max == 100000


def test_missing_criterion_score_treated_as_zero():
    scores = {}  # outcomes not scored
    result = derive_award_range(scores, GRANT_CONFIG_WITH_RULES)
    # outcomes=0 is lt 3, so standard_tier matches
    assert result is not None
    assert result.rule_id == "standard_tier"


def test_flat_fallback_when_no_rules():
    scores = {"outcomes": 3}
    result = derive_award_range(scores, GRANT_CONFIG_FLAT_ONLY)
    assert result is not None
    assert result.rule_id is None
    assert result.rule_label == "Standard award range"
    assert result.award_min == 50000
    assert result.award_max == 200000


def test_returns_none_when_no_config():
    result = derive_award_range({}, {})
    assert result is None


def test_rules_evaluated_in_order_first_match_wins():
    # Both rules could theoretically match if we flip operator logic --
    # confirm first rule in list wins when score=3
    scores = {"outcomes": 3}
    result = derive_award_range(scores, GRANT_CONFIG_WITH_RULES)
    assert result.rule_id == "high_tier"


# ---------------------------------------------------------------------------
# check_scale_up_eligibility
# ---------------------------------------------------------------------------


def test_scale_up_eligible_when_all_criteria_meet_threshold():
    scores = {"deliverability1": 3, "deliverability2": 3}
    eligible, reason = check_scale_up_eligibility(scores, GRANT_CONFIG_WITH_RULES)
    assert eligible is True
    assert "300,000" in reason


def test_scale_up_not_eligible_when_one_criterion_below_threshold():
    scores = {"deliverability1": 3, "deliverability2": 2}
    eligible, reason = check_scale_up_eligibility(scores, GRANT_CONFIG_WITH_RULES)
    assert eligible is False
    assert "deliverability2" in reason


def test_scale_up_not_eligible_when_criteria_missing():
    scores = {}
    eligible, reason = check_scale_up_eligibility(scores, GRANT_CONFIG_WITH_RULES)
    assert eligible is False


def test_scale_up_returns_false_when_no_clause():
    eligible, reason = check_scale_up_eligibility({"skills": 3}, GRANT_CONFIG_FLAT_ONLY)
    assert eligible is False
    assert "No scale-up clause" in reason
