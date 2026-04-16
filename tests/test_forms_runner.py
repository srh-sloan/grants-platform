"""Tests for the JSON form runner helpers — locks the pinned schema contract."""

from __future__ import annotations

import json
import pathlib

import pytest

from app.forms_runner import (
    SUPPORTED_FIELD_TYPES,
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
