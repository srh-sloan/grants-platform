"""Tests for the JSON form runner helpers — locks the pinned schema contract."""

from __future__ import annotations

import pytest

from app.forms_runner import (
    SUPPORTED_FIELD_TYPES,
    EligibilityResult,
    evaluate_eligibility,
    format_answer,
    get_page,
    list_pages,
    merge_page_answers,
    next_page_id,
    validate_page,
)

SCHEMA = {
    "id": "test-form",
    "version": 1,
    "kind": "application",
    "pages": [
        {
            "id": "p1",
            "title": "One",
            "fields": [
                {"id": "name", "type": "text", "label": "Name", "required": True},
                {"id": "bio", "type": "textarea", "label": "Bio", "required": False},
            ],
        },
        {
            "id": "p2",
            "title": "Two",
            "fields": [
                {"id": "age", "type": "number", "label": "Age", "required": True},
            ],
        },
    ],
}


def test_list_pages_returns_order():
    assert [p["id"] for p in list_pages(SCHEMA)] == ["p1", "p2"]


def test_get_page_finds_and_misses():
    assert get_page(SCHEMA, "p1")["title"] == "One"
    assert get_page(SCHEMA, "missing") is None


def test_next_page_id_walks_forward():
    assert next_page_id(SCHEMA, "p1") == "p2"
    assert next_page_id(SCHEMA, "p2") is None


def test_validate_page_required_missing():
    errors = validate_page(SCHEMA["pages"][0], {"bio": "anything"})
    assert "name" in errors
    assert "bio" not in errors


def test_validate_page_accepts_valid():
    assert validate_page(SCHEMA["pages"][0], {"name": "Alice"}) == {}


def test_validate_page_rejects_whitespace_only():
    assert "name" in validate_page(SCHEMA["pages"][0], {"name": "   "})


def test_validate_page_raises_on_unsupported_field_type():
    bad_page = {"fields": [{"id": "x", "type": "made-up", "required": False}]}
    with pytest.raises(ValueError, match="unsupported type"):
        validate_page(bad_page, {})


def test_merge_page_answers_preserves_other_pages():
    existing = {"p1": {"name": "Alice"}}
    merged = merge_page_answers(existing, "p2", {"age": 30})
    assert merged == {"p1": {"name": "Alice"}, "p2": {"age": 30}}
    # Existing dict is not mutated.
    assert existing == {"p1": {"name": "Alice"}}


def test_supported_field_types_match_contract():
    assert frozenset(
        {"text", "textarea", "radio", "checkbox", "select", "number", "currency", "date", "file"}
    ) == SUPPORTED_FIELD_TYPES


# --- evaluate_eligibility ---

# Copied verbatim from seed/grants/ehcf.json — no file I/O in tests.
EHCF_RULES: list[dict] = [
    {
        "id": "org_type",
        "type": "in",
        "label": "Organisation type must be charity, CIO, CIC, CBS or PCC",
        "values": ["charity", "CIO", "CIC", "CBS", "PCC"],
    },
    {
        "id": "operates_in_england",
        "type": "equals",
        "label": "Organisation operates in England",
        "value": True,
    },
    {
        "id": "annual_income",
        "type": "max",
        "label": "Annual income no greater than £5,000,000",
        "value": 5000000,
    },
    {
        "id": "years_serving_homeless",
        "type": "min",
        "label": "At least 3 years delivering services to people rough sleeping or at risk of rough sleeping",
        "value": 3,
    },
    {
        "id": "la_endorsement",
        "type": "equals",
        "label": "Local authority homelessness lead endorsement letter available",
        "value": True,
    },
]

VALID_EHCF_ANSWERS: dict = {
    "org_type": "charity",
    "operates_in_england": True,
    "annual_income": 250000,
    "years_serving_homeless": 5,
    "la_endorsement": True,
}


def test_all_ehcf_rules_pass_with_valid_answers():
    result = evaluate_eligibility(EHCF_RULES, VALID_EHCF_ANSWERS)
    assert result.passed is True
    assert result.failures == []


def test_in_rule_fails_when_org_type_not_in_allowed_list():
    answers = {**VALID_EHCF_ANSWERS, "org_type": "limited_company"}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is False
    assert "org_type" in result.failures


def test_equals_fails_when_operates_in_england_is_no():
    answers = {**VALID_EHCF_ANSWERS, "operates_in_england": "no"}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is False
    assert "operates_in_england" in result.failures


def test_equals_passes_when_answer_is_string_true_and_expected_is_bool_true():
    answers = {**VALID_EHCF_ANSWERS, "operates_in_england": "true", "la_endorsement": "true"}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is True
    assert "operates_in_england" not in result.failures
    assert "la_endorsement" not in result.failures


def test_max_fails_when_annual_income_too_high():
    answers = {**VALID_EHCF_ANSWERS, "annual_income": 6_000_000}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is False
    assert "annual_income" in result.failures


def test_max_passes_at_boundary():
    answers = {**VALID_EHCF_ANSWERS, "annual_income": 5_000_000}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is True
    assert "annual_income" not in result.failures


def test_min_fails_when_years_serving_homeless_too_low():
    answers = {**VALID_EHCF_ANSWERS, "years_serving_homeless": 2}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is False
    assert "years_serving_homeless" in result.failures


def test_min_passes_at_boundary():
    answers = {**VALID_EHCF_ANSWERS, "years_serving_homeless": 3}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is True
    assert "years_serving_homeless" not in result.failures


def test_missing_answer_causes_rule_to_fail():
    answers = {k: v for k, v in VALID_EHCF_ANSWERS.items() if k != "org_type"}
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is False
    assert "org_type" in result.failures


def test_multiple_failures_appear_in_declaration_order():
    answers = {
        **VALID_EHCF_ANSWERS,
        "org_type": "limited_company",    # rule index 0 — fails
        "annual_income": 6_000_000,       # rule index 2 — fails
    }
    result = evaluate_eligibility(EHCF_RULES, answers)
    assert result.passed is False
    assert result.failures == ["org_type", "annual_income"]


def test_unknown_rule_type_raises_value_error():
    bad_rules = [{"id": "x", "type": "nonexistent", "label": "X", "value": 1}]
    with pytest.raises(ValueError, match="Unknown rule type"):
        evaluate_eligibility(bad_rules, {"x": 1})


def test_labels_contains_every_rule_regardless_of_pass_fail():
    # Fail the first rule deliberately so some rules pass and some fail.
    answers = {**VALID_EHCF_ANSWERS, "org_type": "limited_company"}
    result = evaluate_eligibility(EHCF_RULES, answers)
    expected_ids = {rule["id"] for rule in EHCF_RULES}
    assert set(result.labels.keys()) == expected_ids
    # Spot-check one label value.
    assert result.labels["org_type"] == "Organisation type must be charity, CIO, CIC, CBS or PCC"


# ---------------------------------------------------------------------------
# format_answer (P2.4)
# ---------------------------------------------------------------------------

_CURRENCY_FIELD = {"id": "annual_income", "type": "currency", "label": "Annual income"}
_RADIO_FIELD = {
    "id": "org_type",
    "type": "radio",
    "label": "Organisation type",
    "options": [
        {"value": "charity", "label": "Registered charity"},
        {"value": "CIO", "label": "Charitable Incorporated Organisation (CIO)"},
    ],
}
_SELECT_FIELD = {
    "id": "region",
    "type": "select",
    "label": "Region",
    "options": [
        {"value": "north", "label": "North England"},
        {"value": "south", "label": "South England"},
    ],
}
_CHECKBOX_FIELD = {"id": "agree_terms", "type": "checkbox", "label": "I agree"}
_NUMBER_FIELD = {"id": "years", "type": "number", "label": "Years"}
_TEXT_FIELD = {"id": "name", "type": "text", "label": "Name"}
_TEXTAREA_FIELD = {"id": "bio", "type": "textarea", "label": "Bio"}


def test_format_answer_currency_50000():
    assert format_answer(_CURRENCY_FIELD, "50000") == "£50,000"


def test_format_answer_currency_200000():
    assert format_answer(_CURRENCY_FIELD, "200000") == "£200,000"


def test_format_answer_currency_invalid_falls_back():
    result = format_answer(_CURRENCY_FIELD, "not-a-number")
    assert result == "not-a-number"


def test_format_answer_radio_matching_option_returns_label():
    assert format_answer(_RADIO_FIELD, "charity") == "Registered charity"


def test_format_answer_radio_no_match_returns_raw():
    assert format_answer(_RADIO_FIELD, "unknown_value") == "unknown_value"


def test_format_answer_select_matching_option_returns_label():
    assert format_answer(_SELECT_FIELD, "north") == "North England"


def test_format_answer_checkbox_true():
    assert format_answer(_CHECKBOX_FIELD, True) == "Yes"


def test_format_answer_checkbox_string_true():
    assert format_answer(_CHECKBOX_FIELD, "true") == "Yes"


def test_format_answer_checkbox_false():
    assert format_answer(_CHECKBOX_FIELD, False) == "No"


def test_format_answer_checkbox_empty_string():
    assert format_answer(_CHECKBOX_FIELD, "") == ""


def test_format_answer_number_whole():
    assert format_answer(_NUMBER_FIELD, "42") == "42"


def test_format_answer_number_decimal():
    assert format_answer(_NUMBER_FIELD, "3.5") == "3.5"


def test_format_answer_number_whole_float():
    assert format_answer(_NUMBER_FIELD, "3.0") == "3"


def test_format_answer_none_returns_empty():
    assert format_answer(_TEXT_FIELD, None) == ""


def test_format_answer_empty_string_returns_empty():
    assert format_answer(_TEXT_FIELD, "") == ""


def test_format_answer_text_passthrough():
    assert format_answer(_TEXT_FIELD, "Alice Appleton") == "Alice Appleton"


def test_format_answer_textarea_passthrough():
    assert format_answer(_TEXTAREA_FIELD, "Some long answer.") == "Some long answer."
