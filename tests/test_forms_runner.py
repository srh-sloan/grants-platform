"""Tests for the JSON form runner helpers — locks the pinned schema contract."""

from __future__ import annotations

import json
import pathlib

import pytest

from app.forms_runner import (
    SUPPORTED_FIELD_TYPES,
    get_page,
    is_field_visible,
    list_pages,
    merge_page_answers,
    next_page_id,
    validate_page,
    visible_fields,
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
# word_limit validation (P4.2)
# ---------------------------------------------------------------------------

_WORD_LIMIT_PAGE = {
    "fields": [
        {
            "id": "summary",
            "type": "textarea",
            "label": "Summary",
            "required": True,
            "word_limit": 5,
        }
    ]
}

_OPTIONAL_WORD_LIMIT_PAGE = {
    "fields": [
        {
            "id": "notes",
            "type": "textarea",
            "label": "Notes",
            "required": False,
            "word_limit": 5,
        }
    ]
}


def test_word_limit_under_limit():
    errors = validate_page(_WORD_LIMIT_PAGE, {"summary": "one two three four"})
    assert "summary" not in errors


def test_word_limit_at_boundary():
    errors = validate_page(_WORD_LIMIT_PAGE, {"summary": "one two three four five"})
    assert "summary" not in errors


def test_word_limit_over_limit():
    errors = validate_page(_WORD_LIMIT_PAGE, {"summary": "one two three four five six"})
    assert "summary" in errors
    assert "5 words or fewer" in errors["summary"]
    assert "6 words" in errors["summary"]


def test_word_limit_empty_optional_no_error():
    errors = validate_page(_OPTIONAL_WORD_LIMIT_PAGE, {"notes": ""})
    assert "notes" not in errors


def test_word_limit_empty_required_gives_required_error_not_word_count():
    errors = validate_page(_WORD_LIMIT_PAGE, {"summary": ""})
    assert "summary" in errors
    assert errors["summary"] == "This field is required"
    assert "words" not in errors["summary"]


def test_word_limit_ignored_on_text_field():
    # word_limit on a non-textarea field must not trigger word-count validation
    page = {
        "fields": [
            {"id": "tag", "type": "text", "label": "Tag", "required": False, "word_limit": 3}
        ]
    }
    errors = validate_page(page, {"tag": " ".join(["word"] * 10)})
    assert "tag" not in errors


def test_word_limit_and_required_violation_on_different_fields():
    page = {
        "fields": [
            {"id": "title", "type": "text", "label": "Title", "required": True},
            {
                "id": "body",
                "type": "textarea",
                "label": "Body",
                "required": False,
                "word_limit": 3,
            },
        ]
    }
    errors = validate_page(page, {"title": "", "body": "one two three four"})
    assert "title" in errors
    assert "body" in errors


def test_ehcf_local_challenge_and_project_summary_have_word_limit():
    schema_path = pathlib.Path("app/forms/ehcf-application-v1.json")
    schema = json.loads(schema_path.read_text())
    fields_by_id = {
        field["id"]: field
        for page in schema["pages"]
        for field in page["fields"]
    }
    assert fields_by_id["local_challenge"].get("word_limit") == 500
    assert fields_by_id["project_summary"].get("word_limit") == 500


# ---------------------------------------------------------------------------
# Numeric format validation (number / currency)
# ---------------------------------------------------------------------------

_NUMBER_PAGE = {
    "fields": [
        {"id": "count", "type": "number", "label": "Count", "required": True},
    ]
}

_CURRENCY_PAGE = {
    "fields": [
        {"id": "amount", "type": "currency", "label": "Amount", "required": True},
    ]
}

_OPTIONAL_NUMBER_PAGE = {
    "fields": [
        {"id": "count", "type": "number", "label": "Count", "required": False},
    ]
}


def test_number_rejects_non_numeric_text():
    errors = validate_page(_NUMBER_PAGE, {"count": "Numquam explicabo R"})
    assert "count" in errors
    assert errors["count"] == "Enter a number"


def test_number_accepts_integer_string():
    assert validate_page(_NUMBER_PAGE, {"count": "42"}) == {}


def test_number_accepts_decimal_string():
    assert validate_page(_NUMBER_PAGE, {"count": "3.14"}) == {}


def test_number_accepts_negative():
    assert validate_page(_NUMBER_PAGE, {"count": "-5"}) == {}


def test_number_accepts_native_int():
    assert validate_page(_NUMBER_PAGE, {"count": 42}) == {}


def test_currency_rejects_non_numeric_text():
    errors = validate_page(_CURRENCY_PAGE, {"amount": "Numquam explicabo R"})
    assert "amount" in errors
    assert errors["amount"] == "Enter an amount, like 50000"


def test_currency_accepts_plain_number():
    assert validate_page(_CURRENCY_PAGE, {"amount": "50000"}) == {}


def test_currency_accepts_formatted_with_commas_and_pound():
    assert validate_page(_CURRENCY_PAGE, {"amount": "£50,000"}) == {}
    assert validate_page(_CURRENCY_PAGE, {"amount": "50,000"}) == {}
    assert validate_page(_CURRENCY_PAGE, {"amount": "£50000"}) == {}


def test_number_empty_required_reports_required_not_format():
    errors = validate_page(_NUMBER_PAGE, {"count": ""})
    assert errors == {"count": "This field is required"}


def test_number_empty_optional_no_error():
    assert validate_page(_OPTIONAL_NUMBER_PAGE, {"count": ""}) == {}


def test_number_whitespace_only_treated_as_empty_required():
    errors = validate_page(_NUMBER_PAGE, {"count": "   "})
    assert errors == {"count": "This field is required"}


def test_number_rejects_value_with_trailing_letters():
    errors = validate_page(_NUMBER_PAGE, {"count": "42abc"})
    assert "count" in errors


def test_numeric_validation_skipped_for_hidden_field():
    """A hidden number field must not be validated, even with rubbish value."""
    page = {
        "fields": [
            {
                "id": "funding_type",
                "type": "radio",
                "label": "Funding type",
                "required": True,
                "options": [
                    {"value": "revenue", "label": "Revenue"},
                    {"value": "capital", "label": "Capital"},
                ],
            },
            {
                "id": "capital_amount",
                "type": "currency",
                "label": "Capital amount",
                "required": True,
                "visible_when": {
                    "field": "funding_type",
                    "operator": "equals",
                    "value": "capital",
                },
            },
        ]
    }
    errors = validate_page(
        page, {"funding_type": "revenue", "capital_amount": "garbage"}
    )
    assert errors == {}


# ---------------------------------------------------------------------------
# Conditional visibility — is_field_visible (P4.3)
# ---------------------------------------------------------------------------

_CONDITIONAL_FIELD = {
    "id": "capital_readiness",
    "type": "textarea",
    "label": "Describe your capital readiness",
    "required": True,
    "visible_when": {
        "field": "funding_type",
        "operator": "in",
        "value": ["capital", "both"],
    },
}

_UNCONDITIONAL_FIELD = {
    "id": "project_name",
    "type": "text",
    "label": "Project name",
    "required": True,
}


def test_is_field_visible_no_condition():
    """A field without visible_when is always visible."""
    assert is_field_visible(_UNCONDITIONAL_FIELD, {}) is True
    assert is_field_visible(_UNCONDITIONAL_FIELD, {"anything": "value"}) is True


def test_is_field_visible_in_operator_match():
    """'in' operator returns True when the trigger value is in the list."""
    assert is_field_visible(_CONDITIONAL_FIELD, {"funding_type": "capital"}) is True
    assert is_field_visible(_CONDITIONAL_FIELD, {"funding_type": "both"}) is True


def test_is_field_visible_in_operator_no_match():
    """'in' operator returns False when the trigger value is not in the list."""
    assert is_field_visible(_CONDITIONAL_FIELD, {"funding_type": "revenue"}) is False
    # Missing trigger field also means not visible.
    assert is_field_visible(_CONDITIONAL_FIELD, {}) is False


def test_is_field_visible_equals_operator():
    """'equals' operator compares against a single value."""
    field = {
        "id": "detail",
        "type": "text",
        "label": "Detail",
        "required": False,
        "visible_when": {"field": "choice", "operator": "equals", "value": "yes"},
    }
    assert is_field_visible(field, {"choice": "yes"}) is True
    assert is_field_visible(field, {"choice": "no"}) is False
    assert is_field_visible(field, {}) is False


def test_is_field_visible_not_equals_operator():
    """'not_equals' operator returns True when the value differs."""
    field = {
        "id": "alt",
        "type": "text",
        "label": "Alt",
        "required": False,
        "visible_when": {"field": "choice", "operator": "not_equals", "value": "no"},
    }
    assert is_field_visible(field, {"choice": "yes"}) is True
    assert is_field_visible(field, {"choice": "no"}) is False
    # Missing trigger value (None != "no") → visible.
    assert is_field_visible(field, {}) is True


def test_visible_fields_filters_correctly():
    """visible_fields returns only the fields that pass their conditions."""
    page = {
        "fields": [
            _UNCONDITIONAL_FIELD,
            _CONDITIONAL_FIELD,
        ]
    }
    # When funding_type is "revenue", the conditional field is hidden.
    result = visible_fields(page, {"funding_type": "revenue"})
    assert len(result) == 1
    assert result[0]["id"] == "project_name"

    # When funding_type is "capital", both are visible.
    result = visible_fields(page, {"funding_type": "capital"})
    assert len(result) == 2


# ---------------------------------------------------------------------------
# validate_page + conditional visibility (P4.3)
# ---------------------------------------------------------------------------

_VIS_PAGE = {
    "fields": [
        {
            "id": "funding_type",
            "type": "radio",
            "label": "Funding type",
            "required": True,
            "options": [
                {"value": "revenue", "label": "Revenue only"},
                {"value": "capital", "label": "Capital only"},
                {"value": "both", "label": "Both"},
            ],
        },
        {
            "id": "capital_readiness",
            "type": "textarea",
            "label": "Capital readiness",
            "required": True,
            "visible_when": {
                "field": "funding_type",
                "operator": "in",
                "value": ["capital", "both"],
            },
        },
    ]
}


def test_validate_page_skips_hidden_required_field():
    """A required field hidden by visible_when must NOT produce an error."""
    errors = validate_page(_VIS_PAGE, {"funding_type": "revenue"})
    assert "capital_readiness" not in errors
    assert errors == {}


def test_validate_page_validates_visible_required_field():
    """A required field shown by visible_when DOES produce an error if blank."""
    errors = validate_page(_VIS_PAGE, {"funding_type": "capital"})
    assert "capital_readiness" in errors
    assert errors["capital_readiness"] == "This field is required"


def test_validate_page_visible_field_passes_when_filled():
    """A visible required field passes validation when a value is provided."""
    errors = validate_page(
        _VIS_PAGE,
        {"funding_type": "both", "capital_readiness": "We have planning permission."},
    )
    assert errors == {}


# ---------------------------------------------------------------------------
# EHCF schema: conditional fields present (P4.3)
# ---------------------------------------------------------------------------


def test_ehcf_funding_page_has_conditional_capital_fields():
    """The EHCF funding page has visible_when capital readiness fields."""
    schema_path = pathlib.Path("app/forms/ehcf-application-v1.json")
    schema = json.loads(schema_path.read_text())
    funding_page = next(p for p in schema["pages"] if p["id"] == "funding")
    conditional_ids = [
        f["id"] for f in funding_page["fields"] if f.get("visible_when")
    ]
    assert "planning_permission" in conditional_ids
    assert "contractor_identified" in conditional_ids
    assert "capital_readiness" in conditional_ids


# ---------------------------------------------------------------------------
# Local Digital partnership schema (P4.4)
# ---------------------------------------------------------------------------


def _load_local_digital_schema() -> dict:
    path = pathlib.Path("app/forms/local-digital-application-v1.json")
    return json.loads(path.read_text())


def test_local_digital_schema_loads_and_has_pages():
    schema = _load_local_digital_schema()
    assert schema["id"] == "local-digital-application"
    assert schema["version"] == 1
    page_ids = [p["id"] for p in schema["pages"]]
    assert "partnership" in page_ids
    assert "organisation" in page_ids


def test_local_digital_partnership_page_has_conditional_fields():
    """Partnership detail fields are conditional on is_partnership == 'yes'."""
    schema = _load_local_digital_schema()
    partnership_page = next(p for p in schema["pages"] if p["id"] == "partnership")
    conditional_ids = [
        f["id"] for f in partnership_page["fields"] if f.get("visible_when")
    ]
    assert "lead_org_role" in conditional_ids
    assert "partner1_name" in conditional_ids
    assert "partner1_role" in conditional_ids


def test_local_digital_partnership_fields_hidden_when_not_partnership():
    """Partnership fields are hidden when is_partnership is 'no'."""
    schema = _load_local_digital_schema()
    partnership_page = next(p for p in schema["pages"] if p["id"] == "partnership")
    answers = {"is_partnership": "no"}
    vis = visible_fields(partnership_page, answers)
    visible_ids = [f["id"] for f in vis]
    assert "is_partnership" in visible_ids
    assert "partner1_name" not in visible_ids
    assert "lead_org_role" not in visible_ids


def test_local_digital_partnership_fields_shown_when_partnership():
    """Partnership fields appear when is_partnership is 'yes'."""
    schema = _load_local_digital_schema()
    partnership_page = next(p for p in schema["pages"] if p["id"] == "partnership")
    answers = {"is_partnership": "yes"}
    vis = visible_fields(partnership_page, answers)
    visible_ids = [f["id"] for f in vis]
    assert "is_partnership" in visible_ids
    assert "partner1_name" in visible_ids
    assert "lead_org_role" in visible_ids


def test_local_digital_all_field_types_supported():
    """Every field type in the schema is in SUPPORTED_FIELD_TYPES."""
    schema = _load_local_digital_schema()
    for page in schema["pages"]:
        for field in page["fields"]:
            assert field["type"] in SUPPORTED_FIELD_TYPES, (
                f"Field {field['id']!r} has unsupported type {field['type']!r}"
            )
