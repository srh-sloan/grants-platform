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
    assert "There are no grants open for applications at the moment" in body


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


def test_healthz_reports_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_unknown_route_renders_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert "Page not found" in response.get_data(as_text=True)


def test_stream_blueprints_registered(app):
    """Each stream's blueprint URL prefix must be reachable (placeholder or real)."""
    expected = {"public", "auth", "applicant", "assessor"}
    assert expected <= set(app.blueprints)


def test_applicant_queue_requires_login(client):
    """Role-gated routes must redirect anonymous users to auth.login."""
    response = client.get("/apply/", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_assessor_queue_requires_login(client):
    response = client.get("/assess/", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_about_page_returns_200(client):
    """The /about page is public and contains expected content."""
    response = client.get("/about")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "GrantOS" in body
    assert "Scoring model" in body
