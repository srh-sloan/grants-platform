"""Tests for the forms/page.html template.

Renders the template directly via render_template inside
app.test_request_context() — no route is invoked.
"""

from __future__ import annotations

import types

from flask import render_template


def _make_context(
    page: dict,
    answers: dict | None = None,
    errors: dict | None = None,
    back_url: str | None = None,
    action_url: str = "/apply/1/test-page",
    grant_name: str = "EHCF Test",
    app_id: int = 1,
):
    """Build a minimal template context dict."""
    grant = types.SimpleNamespace(name=grant_name)
    application = types.SimpleNamespace(id=app_id, grant=grant)
    form = types.SimpleNamespace()
    return {
        "application": application,
        "form": form,
        "page": page,
        "answers": answers or {},
        "errors": errors or {},
        "action_url": action_url,
        "back_url": back_url,
    }


def _render(app, page: dict, **kwargs) -> str:
    """Render the template and return the HTML string."""
    ctx = _make_context(page, **kwargs)
    with app.test_request_context():
        return render_template("forms/page.html", **ctx)


# ---------------------------------------------------------------------------
# Individual field types
# ---------------------------------------------------------------------------


def test_text_field_renders_label(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [
            {"id": "org_name", "type": "text", "label": "Organisation name", "required": True}
        ],
    }
    html = _render(app, page)
    assert "Organisation name" in html


def test_radio_field_renders_option_labels(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [
            {
                "id": "org_type",
                "type": "radio",
                "label": "Organisation type",
                "required": True,
                "options": [
                    {"value": "charity", "label": "Registered charity"},
                    {"value": "CIO", "label": "Charitable Incorporated Organisation"},
                ],
            }
        ],
    }
    html = _render(app, page)
    assert "Registered charity" in html
    assert "Charitable Incorporated Organisation" in html


def test_textarea_field_renders_textarea_element(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [
            {
                "id": "project_summary",
                "type": "textarea",
                "label": "Project summary",
                "required": True,
            }
        ],
    }
    html = _render(app, page)
    assert "<textarea" in html
    assert "Project summary" in html


def test_currency_field_renders_pound_prefix(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [
            {
                "id": "annual_income",
                "type": "currency",
                "label": "Annual income",
                "required": True,
            }
        ],
    }
    html = _render(app, page)
    assert "£" in html


def test_checkbox_field_renders_checkbox_input(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [
            {
                "id": "agree_terms",
                "type": "checkbox",
                "label": "I confirm the information is accurate",
                "required": True,
            }
        ],
    }
    html = _render(app, page)
    assert 'type="checkbox"' in html
    assert "I confirm the information is accurate" in html


# ---------------------------------------------------------------------------
# Error summary
# ---------------------------------------------------------------------------


def test_error_summary_present_when_errors(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [{"id": "name", "type": "text", "label": "Name", "required": True}],
    }
    html = _render(app, page, errors={"name": "This field is required"})
    assert "There is a problem" in html
    assert "This field is required" in html


def test_error_summary_absent_when_no_errors(app):
    page = {
        "id": "p1",
        "title": "Test page",
        "fields": [{"id": "name", "type": "text", "label": "Name", "required": True}],
    }
    html = _render(app, page, errors={})
    assert "There is a problem" not in html


# ---------------------------------------------------------------------------
# Back link
# ---------------------------------------------------------------------------


def test_back_link_present_when_back_url_set(app):
    page = {"id": "p1", "title": "Test page", "fields": []}
    html = _render(app, page, back_url="/apply/1/previous-page")
    assert "govuk-back-link" in html
    assert "/apply/1/previous-page" in html


def test_back_link_absent_when_back_url_none(app):
    page = {"id": "p1", "title": "Test page", "fields": []}
    html = _render(app, page, back_url=None)
    assert "govuk-back-link" not in html


# ---------------------------------------------------------------------------
# Form action
# ---------------------------------------------------------------------------


def test_form_action_attribute_contains_action_url(app):
    page = {"id": "p1", "title": "Test page", "fields": []}
    action = "/apply/42/my-page"
    html = _render(app, page, action_url=action)
    assert action in html


# ---------------------------------------------------------------------------
# Conditional visibility (P4.3)
# ---------------------------------------------------------------------------


def test_conditional_field_hidden_when_condition_not_met(app):
    """A field with visible_when should not render when the condition is false."""
    page = {
        "id": "p1",
        "title": "Funding",
        "fields": [
            {
                "id": "funding_type",
                "type": "radio",
                "label": "Funding type",
                "required": True,
                "options": [
                    {"value": "revenue", "label": "Revenue only"},
                    {"value": "capital", "label": "Capital only"},
                ],
            },
            {
                "id": "capital_readiness",
                "type": "textarea",
                "label": "Describe your capital readiness",
                "required": True,
                "visible_when": {
                    "field": "funding_type",
                    "operator": "in",
                    "value": ["capital", "both"],
                },
            },
        ],
    }
    # When funding_type is "revenue", the conditional field should be hidden.
    html = _render(app, page, answers={"funding_type": "revenue"})
    assert "Describe your capital readiness" not in html


def test_conditional_field_shown_when_condition_met(app):
    """A field with visible_when should render when the condition is true."""
    page = {
        "id": "p1",
        "title": "Funding",
        "fields": [
            {
                "id": "funding_type",
                "type": "radio",
                "label": "Funding type",
                "required": True,
                "options": [
                    {"value": "revenue", "label": "Revenue only"},
                    {"value": "capital", "label": "Capital only"},
                ],
            },
            {
                "id": "capital_readiness",
                "type": "textarea",
                "label": "Describe your capital readiness",
                "required": True,
                "visible_when": {
                    "field": "funding_type",
                    "operator": "in",
                    "value": ["capital", "both"],
                },
            },
        ],
    }
    # When funding_type is "capital", the conditional field should be shown.
    html = _render(app, page, answers={"funding_type": "capital"})
    assert "Describe your capital readiness" in html


def test_conditional_field_hidden_when_no_answers(app):
    """A conditional field is hidden when answers dict is empty."""
    page = {
        "id": "p1",
        "title": "Funding",
        "fields": [
            {
                "id": "capital_readiness",
                "type": "textarea",
                "label": "Describe your capital readiness",
                "required": True,
                "visible_when": {
                    "field": "funding_type",
                    "operator": "in",
                    "value": ["capital", "both"],
                },
            },
        ],
    }
    html = _render(app, page, answers={})
    assert "Describe your capital readiness" not in html
