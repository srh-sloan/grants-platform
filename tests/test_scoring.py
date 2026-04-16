"""Tests for the pure scoring helpers. These lock the cross-stream contract."""

from __future__ import annotations

from app.scoring import (
    calculate_weighted_score,
    has_auto_reject,
    max_weighted_total,
    missing_criteria,
)

# The EHCF-shaped criteria — weights sum to 100, max raw 3.
CRITERIA = [
    {"id": "skills", "label": "Skills", "weight": 10, "max": 3, "auto_reject_on_zero": True},
    {"id": "proposal1", "label": "Proposal 1", "weight": 10, "max": 3, "auto_reject_on_zero": True},
    {"id": "proposal2", "label": "Proposal 2", "weight": 30, "max": 3, "auto_reject_on_zero": True},
    {"id": "deliverability1", "label": "Deliv 1", "weight": 25, "max": 3, "auto_reject_on_zero": True},
    {"id": "deliverability2", "label": "Deliv 2", "weight": 5, "max": 3, "auto_reject_on_zero": True},
    {"id": "cost_value", "label": "Cost", "weight": 10, "max": 3, "auto_reject_on_zero": True},
    {"id": "outcomes", "label": "Outcomes", "weight": 10, "max": 3, "auto_reject_on_zero": True},
]


def test_calculate_weighted_score_all_threes_is_max():
    scores = {c["id"]: 3 for c in CRITERIA}
    assert calculate_weighted_score(scores, CRITERIA) == 300


def test_calculate_weighted_score_mixed():
    scores = {
        "skills": 2, "proposal1": 2, "proposal2": 3, "deliverability1": 2,
        "deliverability2": 1, "cost_value": 2, "outcomes": 2,
    }
    # 2*10 + 2*10 + 3*30 + 2*25 + 1*5 + 2*10 + 2*10 = 225
    assert calculate_weighted_score(scores, CRITERIA) == 225


def test_missing_scores_treated_as_zero():
    assert calculate_weighted_score({}, CRITERIA) == 0


def test_has_auto_reject_triggers_on_zero():
    scores = {c["id"]: 3 for c in CRITERIA} | {"proposal2": 0}
    assert has_auto_reject(scores, CRITERIA) is True


def test_has_auto_reject_false_when_all_nonzero():
    scores = {c["id"]: 1 for c in CRITERIA}
    assert has_auto_reject(scores, CRITERIA) is False


def test_has_auto_reject_ignores_criteria_not_flagged():
    criteria = [
        {"id": "flagged", "weight": 50, "max": 3, "auto_reject_on_zero": True},
        {"id": "unflagged", "weight": 50, "max": 3, "auto_reject_on_zero": False},
    ]
    assert has_auto_reject({"flagged": 2, "unflagged": 0}, criteria) is False


def test_missing_criteria_lists_unscored():
    scores = {"skills": 2, "proposal1": 3}
    assert set(missing_criteria(scores, CRITERIA)) == {
        "proposal2", "deliverability1", "deliverability2", "cost_value", "outcomes",
    }


def test_max_weighted_total_is_sum_of_weight_times_max():
    assert max_weighted_total(CRITERIA) == 300
