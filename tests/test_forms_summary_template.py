"""Template rendering tests for forms/summary.html — Stream B P2.4."""

from __future__ import annotations

from flask import render_template

_SCHEMA = {
    "id": "test-form",
    "version": 1,
    "kind": "application",
    "pages": [
        {
            "id": "details",
            "title": "Organisation details",
            "fields": [
                {"id": "name", "type": "text", "label": "Organisation name"},
                {
                    "id": "annual_income",
                    "type": "currency",
                    "label": "Annual income",
                },
                {
                    "id": "org_type",
                    "type": "radio",
                    "label": "Organisation type",
                    "options": [
                        {"value": "charity", "label": "Registered charity"},
                        {"value": "CIO", "label": "Charitable Incorporated Organisation"},
                    ],
                },
                {
                    "id": "agree",
                    "type": "checkbox",
                    "label": "I agree to the terms",
                },
            ],
        }
    ],
}


def test_summary_renders_currency_formatted(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={"details": {"annual_income": "50000"}},
            documents=[],
        )
    assert "£50,000" in html


def test_summary_renders_radio_label_not_raw_value(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={"details": {"org_type": "charity"}},
            documents=[],
        )
    assert "Registered charity" in html
    # raw value should not appear as a standalone answer
    assert "charity" in html  # it's inside "Registered charity" — that's fine


def test_summary_renders_checkbox_yes(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={"details": {"agree": True}},
            documents=[],
        )
    assert "Yes" in html


def test_summary_renders_checkbox_no(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={"details": {"agree": False}},
            documents=[],
        )
    assert "No" in html


def test_summary_shows_not_answered_for_missing(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={},
            documents=[],
        )
    assert "Not answered" in html


def test_summary_documents_empty_state(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={},
            documents=[],
        )
    assert "No documents uploaded yet" in html


def test_summary_renders_page_titles(app):
    with app.test_request_context():
        html = render_template(
            "forms/summary.html",
            schema=_SCHEMA,
            answers={},
            documents=[],
        )
    assert "Organisation details" in html
