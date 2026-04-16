"""Tests for the JSON form runner helpers — locks the pinned schema contract."""

from __future__ import annotations

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
