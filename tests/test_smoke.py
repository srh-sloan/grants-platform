"""Smoke tests — prove the app boots, the DB roundtrips, and the landing page renders."""

from __future__ import annotations


def test_app_boots(app):
    assert app is not None
    assert "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]


def test_landing_page_renders_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Grants platform" in body
    assert "No grants are open" in body


def test_landing_page_lists_seeded_grant(client, seeded_grant):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert seeded_grant.name in body
    assert seeded_grant.slug in body


def test_govuk_static_assets_available(client):
    """The GOV.UK Frontend CSS + fonts must be reachable at the paths the CSS expects."""
    css = client.get("/static/govuk-frontend.min.css")
    assert css.status_code == 200
    asset = client.get("/assets/images/govuk-crest.svg")
    assert asset.status_code == 200
