"""Template rendering tests for the page progress indicator — Stream B P2.1."""

from __future__ import annotations

import types

from flask import render_template

_SCHEMA_PAGES = [
    {"id": "p1", "title": "One", "fields": []},
    {"id": "p2", "title": "Two", "fields": []},
    {"id": "p3", "title": "Three", "fields": []},
    {"id": "p4", "title": "Four", "fields": []},
    {"id": "p5", "title": "Five", "fields": []},
]


def _make_context(**kwargs):
    grant = types.SimpleNamespace(name="Test Grant")
    application = types.SimpleNamespace(id=1, grant=grant)
    form = types.SimpleNamespace()
    ctx = {
        "application": application,
        "form": form,
        "page": {"id": "p2", "title": "Two", "fields": []},
        "answers": {},
        "errors": {},
        "action_url": "/apply/1/page/p2",
        "back_url": None,
    }
    ctx.update(kwargs)
    return ctx


def test_progress_indicator_renders_when_values_present(app):
    with app.test_request_context():
        html = render_template("forms/page.html", **_make_context(page_number=2, total_pages=5))
    assert "Page 2 of 5" in html


def test_progress_indicator_absent_when_page_number_is_none(app):
    with app.test_request_context():
        html = render_template("forms/page.html", **_make_context(page_number=None, total_pages=5))
    assert "of 5" not in html


def test_progress_indicator_absent_when_neither_value_passed(app):
    with app.test_request_context():
        html = render_template("forms/page.html", **_make_context())
    assert "Page" not in html or "of" not in html


def test_progress_indicator_correct_text(app):
    with app.test_request_context():
        html = render_template("forms/page.html", **_make_context(page_number=3, total_pages=7))
    assert "Page 3 of 7" in html
