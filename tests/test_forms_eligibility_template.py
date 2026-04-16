"""Tests for the eligibility form schema and eligibility_result.html template.

Stream B — Phase 2, P2.2.

Tests cover:
  - ehcf-eligibility-v1.json is valid JSON with the correct schema shape and
    only uses SUPPORTED_FIELD_TYPES.
  - eligibility_result.html renders the passing state correctly.
  - eligibility_result.html renders the failing state correctly, including
    human-readable failure labels, the check-answers link, and the contact email.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from app.forms_runner import SUPPORTED_FIELD_TYPES, EligibilityResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA_PATH = Path(__file__).parent.parent / "app" / "forms" / "ehcf-eligibility-v1.json"


def _make_grant(
    name: str = "Ending Homelessness in Communities Fund",
    contact_email: str | None = "ehcf@communities.gov.uk",
):
    """Return a minimal namespace that quacks like a Grant model for templates."""
    config_json: dict[str, object] = {}
    if contact_email is not None:
        config_json["contact_email"] = contact_email
    return types.SimpleNamespace(name=name, config_json=config_json)


# ---------------------------------------------------------------------------
# Schema file tests
# ---------------------------------------------------------------------------


def test_eligibility_schema_is_valid_json():
    """The file must parse as JSON without errors."""
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    schema = json.loads(text)
    assert isinstance(schema, dict)


def test_eligibility_schema_top_level_keys():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema.get("id") == "ehcf-eligibility"
    assert schema.get("version") == 1
    assert schema.get("kind") == "eligibility"
    assert "pages" in schema


def test_eligibility_schema_has_one_page():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    pages = schema["pages"]
    assert len(pages) == 1
    assert pages[0]["id"] == "eligibility"
    assert "fields" in pages[0]


def test_eligibility_schema_expected_field_ids():
    """All five eligibility rule IDs must have a corresponding form field."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    field_ids = {f["id"] for f in schema["pages"][0]["fields"]}
    expected = {
        "org_type",
        "operates_in_england",
        "annual_income",
        "years_serving_homeless",
        "la_endorsement",
    }
    assert expected == field_ids


def test_eligibility_schema_all_field_types_supported():
    """Every field type must be in SUPPORTED_FIELD_TYPES (contract from forms_runner.py)."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for page in schema["pages"]:
        for field in page["fields"]:
            assert field["type"] in SUPPORTED_FIELD_TYPES, (
                f"Field {field['id']!r} uses unsupported type {field['type']!r}"
            )


def test_eligibility_schema_all_fields_required():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for field in schema["pages"][0]["fields"]:
        assert field.get("required") is True, f"Field {field['id']!r} should be required"


def test_eligibility_schema_radio_fields_have_options():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    radio_fields = [f for f in schema["pages"][0]["fields"] if f["type"] == "radio"]
    assert len(radio_fields) >= 1
    for field in radio_fields:
        assert "options" in field and len(field["options"]) >= 2, (
            f"Radio field {field['id']!r} must have at least two options"
        )


def test_eligibility_schema_boolean_radios_use_string_true_false():
    """Boolean fields (operates_in_england, la_endorsement) must use 'true'/'false' strings."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fields_by_id = {f["id"]: f for f in schema["pages"][0]["fields"]}
    for field_id in ("operates_in_england", "la_endorsement"):
        field = fields_by_id[field_id]
        values = {opt["value"] for opt in field["options"]}
        assert values == {"true", "false"}, (
            f"Field {field_id!r} options must be 'true'/'false' strings, got {values!r}"
        )


# ---------------------------------------------------------------------------
# Template rendering tests
# ---------------------------------------------------------------------------


def _render(app, template_name: str, **context: object) -> str:
    from flask import render_template

    with app.test_request_context():
        return render_template(template_name, **context)


@pytest.fixture()
def passing_result() -> EligibilityResult:
    return EligibilityResult(passed=True, failures=[], labels={})


@pytest.fixture()
def failing_result() -> EligibilityResult:
    return EligibilityResult(
        passed=False,
        failures=["annual_income", "years_serving_homeless"],
        labels={
            "annual_income": "Annual income no greater than £5,000,000",
            "years_serving_homeless": (
                "At least 3 years delivering services to people rough sleeping "
                "or at risk of rough sleeping"
            ),
        },
    )


# Passing state ----------------------------------------------------------------


def test_passing_result_shows_eligible_text(app, passing_result):
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=passing_result,
        grant=_make_grant(),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    assert "eligible" in html.lower()


def test_passing_result_shows_grant_name(app, passing_result):
    grant_name = "Ending Homelessness in Communities Fund"
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=passing_result,
        grant=_make_grant(grant_name),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    assert grant_name in html


def test_passing_result_renders_start_application_link(app, passing_result):
    continue_url = "/apply/start"
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=passing_result,
        grant=_make_grant(),
        continue_url=continue_url,
        check_url="/apply/eligibility",
    )
    assert "Start your application" in html
    assert continue_url in html


# Failing state ----------------------------------------------------------------


def test_failing_result_shows_not_eligible_text(app, failing_result):
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=failing_result,
        grant=_make_grant(),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    assert "does not appear to be eligible" in html


def test_failing_result_lists_human_readable_labels(app, failing_result):
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=failing_result,
        grant=_make_grant(),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    # Human-readable labels must appear — raw rule IDs must not stand alone.
    assert "Annual income no greater than £5,000,000" in html
    assert "At least 3 years delivering services" in html


def test_failing_result_does_not_show_rule_ids_as_labels(app, failing_result):
    """Template should show labels, not bare snake_case rule IDs."""
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=failing_result,
        grant=_make_grant(),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    # The labels contain the human-readable text; rule IDs should NOT appear
    # as standalone bullet-point text.  We allow them to appear in attributes
    # (e.g. aria) but not as visible list item content.  A rough proxy: the
    # raw ID should not appear as a complete line item.
    assert "<li>annual_income</li>" not in html
    assert "<li>years_serving_homeless</li>" not in html


def test_failing_result_shows_check_your_answers_link(app, failing_result):
    check_url = "/apply/eligibility"
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=failing_result,
        grant=_make_grant(),
        continue_url="/apply/start",
        check_url=check_url,
    )
    assert "Check your answers" in html
    assert check_url in html


def test_failing_result_shows_contact_email_from_grant_config(app, failing_result):
    """The contact email must come from grant.config_json, not be hardcoded."""
    custom_email = "support@example.gov.uk"
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=failing_result,
        grant=_make_grant(contact_email=custom_email),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    assert custom_email in html
    assert f"mailto:{custom_email}" in html
    # The previously-hardcoded EHCF address must not leak through for other grants.
    assert "ehcf@communities.gov.uk" not in html


def test_failing_result_omits_contact_block_when_no_email_configured(app, failing_result):
    """If grant config has no contact_email, the contact bullet is hidden."""
    html = _render(
        app,
        "forms/eligibility_result.html",
        result=failing_result,
        grant=_make_grant(contact_email=None),
        continue_url="/apply/start",
        check_url="/apply/eligibility",
    )
    assert "mailto:" not in html
