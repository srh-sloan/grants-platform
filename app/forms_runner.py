"""JSON-driven form runner — pure helpers for schema traversal + validation.

**Stream ownership:** Form runner (Stream B).

The applicant blueprint (Stream A) calls into these helpers; it never walks
the form schema itself. Keep this module free of Flask, DB, and I/O so it can
be unit-tested in isolation.

Schema contract (pinned in Phase 0 — see ``CONTRIBUTING.md``)::

    {
      "id": "ehcf-application",
      "version": 1,
      "kind": "application",
      "pages": [
        {
          "id": "organisation",
          "title": "About your organisation",
          "fields": [
            {"id": "name", "type": "text", "label": "...", "required": true},
            ...
          ]
        }
      ]
    }

Supported field ``type`` values (adding a new type requires a new runner handler
AND a new Jinja macro — coordinate across streams before doing so):

``text``, ``textarea``, ``radio``, ``checkbox``, ``select``, ``number``,
``currency``, ``date``, ``file``.
"""

from __future__ import annotations

SUPPORTED_FIELD_TYPES: frozenset[str] = frozenset(
    {"text", "textarea", "radio", "checkbox", "select", "number", "currency", "date", "file"}
)


# ---------------------------------------------------------------------------
# Schema traversal
# ---------------------------------------------------------------------------


def list_pages(schema: dict) -> list[dict]:
    """Return the pages list in order; empty list if the schema has none."""
    return list(schema.get("pages") or [])


def get_page(schema: dict, page_id: str) -> dict | None:
    """Find a page by its ID, or None if missing."""
    for page in list_pages(schema):
        if page.get("id") == page_id:
            return page
    return None


def next_page_id(schema: dict, current_page_id: str) -> str | None:
    """ID of the page after ``current_page_id``, or None if at the end."""
    pages = list_pages(schema)
    for idx, page in enumerate(pages):
        if page.get("id") == current_page_id and idx + 1 < len(pages):
            return pages[idx + 1]["id"]
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_page(page: dict, submitted: dict) -> dict[str, str]:
    """Validate a single page's submission against its schema.

    Returns a mapping of ``field_id -> error message`` for invalid fields.
    An empty dict means the submission is valid.

    Phase 1 scope: required-field check only. Stream B expands to cover
    numeric ranges, word limits, conditional logic in later phases.
    """
    errors: dict[str, str] = {}
    for field in page.get("fields") or []:
        if field.get("type") not in SUPPORTED_FIELD_TYPES:
            raise ValueError(
                f"Field {field.get('id')!r} has unsupported type {field.get('type')!r}"
            )
        if field.get("required") and not _has_value(submitted.get(field["id"])):
            errors[field["id"]] = "This field is required"
    return errors


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# ---------------------------------------------------------------------------
# Answer merging (draft save)
# ---------------------------------------------------------------------------


def merge_page_answers(
    existing_answers: dict,
    page_id: str,
    page_submission: dict,
) -> dict:
    """Merge a page's submitted fields into the existing ``answers_json`` blob.

    Answers are stored as ``{page_id: {field_id: value}}``. Callers pass the
    full existing blob and the new page data; this returns a new dict
    (existing input is not mutated).
    """
    merged = dict(existing_answers)
    merged[page_id] = {**(merged.get(page_id) or {}), **page_submission}
    return merged
