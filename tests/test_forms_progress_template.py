"""Template rendering tests for the page progress indicator — Stream B P2.1."""

from __future__ import annotations

import types

from flask import render_template

_FIVE_PAGES = [
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
        html = render_template(
            "forms/page.html",
            **_make_context(all_pages=_FIVE_PAGES, current_index=1),
        )
    assert "Page 2 of 5" in html


def test_progress_indicator_absent_when_all_pages_not_passed(app):
    with app.test_request_context():
        html = render_template("forms/page.html", **_make_context())
    assert "Page" not in html or "of" not in html


def test_progress_indicator_correct_text_first_page(app):
    with app.test_request_context():
        html = render_template(
            "forms/page.html",
            **_make_context(all_pages=_FIVE_PAGES, current_index=0),
        )
    assert "Page 1 of 5" in html


def test_progress_indicator_correct_text_last_page(app):
    with app.test_request_context():
        html = render_template(
            "forms/page.html",
            **_make_context(all_pages=_FIVE_PAGES, current_index=4),
        )
    assert "Page 5 of 5" in html
