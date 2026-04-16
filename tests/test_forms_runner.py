"""Tests for the JSON form runner helpers — locks the pinned schema contract."""

from __future__ import annotations

import pytest

from app.forms_runner import (
    SUPPORTED_FIELD_TYPES,
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
