"""Tests for the applicant blueprint — dashboard, form flow, review, submit.

Stream A owns this module. Tests use a seeded EHCF grant + form to exercise
the full round-trip without waiting on Stream D's shared fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models import (
    Application,
    ApplicationStatus,
    Form,
    FormKind,
    Grant,
    GrantStatus,
    Organisation,
    User,
    UserRole,
)

# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

FORMS_DIR = Path(__file__).resolve().parent.parent / "app" / "forms"
GRANTS_DIR = Path(__file__).resolve().parent.parent / "seed" / "grants"


@pytest.fixture
def seeded_ehcf(db):
    """Seed the EHCF grant and its application form from disk.

    Uses the same JSON files the production seed script uses — keeps tests
    honest about the real schema rather than inventing a parallel shape.
    """
    config = json.loads((GRANTS_DIR / "ehcf.json").read_text())
    grant = Grant(
        slug=config["slug"],
        name=config["name"],
        status=GrantStatus(config["status"]),
        config_json=config,
    )
    db.session.add(grant)
    db.session.flush()

    schema = json.loads((FORMS_DIR / "ehcf-application-v1.json").read_text())
    form = Form(
        grant=grant,
        kind=FormKind.APPLICATION,
        version=int(schema.get("version", 1)),
        schema_json=schema,
    )
    db.session.add(form)
    db.session.commit()
    return grant, form


@pytest.fixture
def applicant(db):
    org = Organisation(name="Shelter Test", contact_email="me@test.test")
    db.session.add(org)
    db.session.flush()
    user = User(
        email="me@test.test",
        password_hash=generate_password_hash("correct-password-1234"),
        role=UserRole.APPLICANT,
        org_id=org.id,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def other_org_applicant(db):
    """A second applicant in a different organisation — for cross-tenant tests."""
    org = Organisation(name="Other Org", contact_email="other@test.test")
    db.session.add(org)
    db.session.flush()
    user = User(
        email="other@test.test",
        password_hash=generate_password_hash("correct-password-1234"),
        role=UserRole.APPLICANT,
        org_id=org.id,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def assessor(db):
    user = User(
        email="assessor@test.test",
        password_hash=generate_password_hash("correct-password-1234"),
        role=UserRole.ASSESSOR,
        org_id=None,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user, password="correct-password-1234"):
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_shows_empty_state_for_new_applicant(
    client, applicant, seeded_ehcf
):
    _login(client, applicant)

    response = client.get("/apply/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Your applications" in body
    assert applicant.email in body
    assert "Shelter Test" in body
    assert "haven't started an application" in body
    assert "Ending Homelessness in Communities Fund" in body


def test_dashboard_lists_existing_applications_with_status_tag(
    client, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    application = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.DRAFT,
        answers_json={},
    )
    db.session.add(application)
    db.session.commit()
    _login(client, applicant)

    response = client.get("/apply/")
    body = response.get_data(as_text=True)
    assert "applications-table" in body
    assert "Draft" in body
    assert "Continue" in body


def test_dashboard_hides_grant_cta_when_already_applied(
    client, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    db.session.add(
        Application(
            org_id=applicant.org_id,
            grant_id=grant.id,
            form_version=1,
            status=ApplicationStatus.DRAFT,
        )
    )
    db.session.commit()
    _login(client, applicant)

    response = client.get("/apply/")
    body = response.get_data(as_text=True)
    # The "Start application" button only appears for grants not yet applied to.
    assert "no further open grants" in body


def test_dashboard_requires_applicant_role(client, assessor):
    _login(client, assessor)
    response = client.get("/apply/")
    assert response.status_code == 403


def test_dashboard_redirects_anonymous_to_login(client):
    response = client.get("/apply/", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def test_start_creates_draft_and_redirects_to_first_page(
    client, applicant, seeded_ehcf, db
):
    _login(client, applicant)

    response = client.get("/apply/ehcf/start", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/apply/" in location
    assert "/organisation" in location  # first page id in the EHCF schema

    apps = db.session.execute(
        select(Application).where(Application.org_id == applicant.org_id)
    ).scalars().all()
    assert len(apps) == 1
    assert apps[0].status == ApplicationStatus.DRAFT
    assert apps[0].form_version == 1


def test_start_is_idempotent_across_visits(client, applicant, seeded_ehcf, db):
    _login(client, applicant)

    client.get("/apply/ehcf/start")
    client.get("/apply/ehcf/start")
    client.get("/apply/ehcf/start")

    count = db.session.scalar(
        select(_db.func.count()).select_from(Application).where(
            Application.org_id == applicant.org_id
        )
    )
    assert count == 1


def test_start_404s_on_unknown_grant(client, applicant):
    _login(client, applicant)
    response = client.get("/apply/no-such-grant/start")
    assert response.status_code == 404


def test_start_blocks_closed_grants(client, applicant, db, seeded_ehcf):
    grant, _form = seeded_ehcf
    grant.status = GrantStatus.CLOSED
    db.session.commit()
    _login(client, applicant)

    response = client.get("/apply/ehcf/start", follow_redirects=False)
    assert response.status_code == 302
    assert "/apply/" in response.headers["Location"]


def test_start_on_submitted_application_goes_to_review(
    client, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    app = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
    )
    db.session.add(app)
    db.session.commit()
    _login(client, applicant)

    response = client.get("/apply/ehcf/start", follow_redirects=False)
    assert response.status_code == 302
    assert f"/apply/{app.id}/review" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Form page (GET) and save_page (POST)
# ---------------------------------------------------------------------------


def _start_application(client, applicant, seeded_ehcf) -> Application:
    _login(client, applicant)
    client.get("/apply/ehcf/start")
    return _db.session.execute(
        select(Application).where(Application.org_id == applicant.org_id)
    ).scalar_one()


def test_form_page_renders_for_owned_draft(client, applicant, seeded_ehcf):
    app = _start_application(client, applicant, seeded_ehcf)
    response = client.get(f"/apply/{app.id}/organisation")
    assert response.status_code == 200


def test_form_page_renders_progress_indicator(client, applicant, seeded_ehcf):
    """The page.html template only renders 'Page X of Y' when both
    page_number and total_pages are passed — regression test for the
    context-name mismatch that previously suppressed the progress line."""
    _grant, form = seeded_ehcf
    total_pages = len(form.schema_json["pages"])
    app = _start_application(client, applicant, seeded_ehcf)

    response = client.get(f"/apply/{app.id}/organisation")
    body = response.get_data(as_text=True)
    assert f"Page 1 of {total_pages}" in body


def test_form_page_404s_on_unknown_application(client, applicant, seeded_ehcf):
    _login(client, applicant)
    response = client.get("/apply/9999/organisation")
    assert response.status_code == 404


def test_form_page_404s_on_other_orgs_application(
    client, other_org_applicant, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    # Draft owned by applicant, but the other_org user is logged in.
    app = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.DRAFT,
    )
    db.session.add(app)
    db.session.commit()

    _login(client, other_org_applicant)
    response = client.get(f"/apply/{app.id}/organisation")
    assert response.status_code == 404


def test_form_page_404s_on_unknown_page_id(client, applicant, seeded_ehcf):
    app = _start_application(client, applicant, seeded_ehcf)
    response = client.get(f"/apply/{app.id}/no-such-page")
    assert response.status_code == 404


def test_form_page_redirects_submitted_to_review(
    client, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    app = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
    )
    db.session.add(app)
    db.session.commit()
    _login(client, applicant)

    response = client.get(f"/apply/{app.id}/organisation", follow_redirects=False)
    assert response.status_code == 302
    assert f"/apply/{app.id}/review" in response.headers["Location"]


def test_save_page_persists_draft_and_advances(
    client, applicant, seeded_ehcf, db
):
    app = _start_application(client, applicant, seeded_ehcf)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/proposal" in response.headers["Location"]  # next page

    db.session.refresh(app)
    assert "organisation" in app.answers_json
    assert app.answers_json["organisation"]["name"] == "Shelter Bristol"
    assert app.answers_json["organisation"]["org_type"] == "charity"
    assert app.status == ApplicationStatus.DRAFT


def test_save_page_returns_400_with_errors_on_missing_required(
    client, applicant, seeded_ehcf
):
    app = _start_application(client, applicant, seeded_ehcf)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={"name": "", "bio": "ignored"},
    )
    # Re-renders the same page with errors (400).
    assert response.status_code == 400


def test_save_page_strips_whitespace(client, applicant, seeded_ehcf, db):
    app = _start_application(client, applicant, seeded_ehcf)

    client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "  Shelter Bristol  ",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )
    db.session.refresh(app)
    assert app.answers_json["organisation"]["name"] == "Shelter Bristol"


def test_save_page_second_page_preserves_first(
    client, applicant, seeded_ehcf, db
):
    app = _start_application(client, applicant, seeded_ehcf)

    client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )
    client.post(
        f"/apply/{app.id}/proposal",
        data={
            "project_name": "Pathways Out",
            "fund_objective": "community_support",
            "local_challenge": "Locally we see X...",
            "project_summary": "We will...",
        },
    )

    db.session.refresh(app)
    assert "organisation" in app.answers_json
    assert "proposal" in app.answers_json
    assert app.answers_json["organisation"]["name"] == "Shelter Bristol"


def test_save_page_on_submitted_application_is_blocked(
    client, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    app = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
    )
    db.session.add(app)
    db.session.commit()
    _login(client, applicant)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={"name": "Late Edit"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/apply/{app.id}/review" in response.headers["Location"]

    db.session.refresh(app)
    assert app.answers_json in ({}, None)


def test_last_page_redirects_to_review(client, applicant, seeded_ehcf):
    app = _start_application(client, applicant, seeded_ehcf)
    response = client.post(
        f"/apply/{app.id}/declaration",
        data={
            "contact_name": "Alice",
            "contact_email": "alice@test.test",
            "agree_terms": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/review" in response.headers["Location"]


def test_draft_persists_across_login_cycles(
    client, applicant, seeded_ehcf, db
):
    """Register -> save page -> sign out -> sign back in -> draft still there."""
    app = _start_application(client, applicant, seeded_ehcf)
    client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )
    client.post("/auth/logout")
    # Now sign back in.
    client.post(
        "/auth/login",
        data={"email": applicant.email, "password": "correct-password-1234"},
    )

    dashboard = client.get("/apply/")
    body = dashboard.get_data(as_text=True)
    assert "Ending Homelessness" in body
    assert "Draft" in body


# ---------------------------------------------------------------------------
# Review + Submit
# ---------------------------------------------------------------------------


def _fill_all_pages(client, app_id: int) -> None:
    """POST answers to every page, enough to satisfy required-field validation."""
    client.post(
        f"/apply/{app_id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )
    client.post(
        f"/apply/{app_id}/proposal",
        data={
            "project_name": "Pathways Out",
            "fund_objective": "community_support",
            "local_challenge": "Locally we see 200 rough sleepers...",
            "project_summary": "We will provide outreach and recovery support...",
        },
    )
    client.post(
        f"/apply/{app_id}/funding",
        data={
            "funding_type": "revenue",
            "revenue_amount": "180000",
        },
    )
    client.post(
        f"/apply/{app_id}/deliverability",
        data={
            "milestones": "Q1 recruitment, Q2 rollout",
            "risks": "Staffing; mitigated by partner org",
            "la_endorsement": "letter-on-file.pdf",
        },
    )
    client.post(
        f"/apply/{app_id}/declaration",
        data={
            "contact_name": "Alice Applicant",
            "contact_email": "alice@test.test",
            "agree_terms": "on",
        },
    )


def test_review_page_renders_answers(client, applicant, seeded_ehcf):
    app = _start_application(client, applicant, seeded_ehcf)
    _fill_all_pages(client, app.id)

    response = client.get(f"/apply/{app.id}/review")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Check your answers" in body
    assert "Shelter Bristol" in body
    assert "Pathways Out" in body
    assert "answers-summary" in body


def test_review_page_lists_missing_pages_for_incomplete_draft(
    client, applicant, seeded_ehcf
):
    app = _start_application(client, applicant, seeded_ehcf)
    # Intentionally skip most pages.
    client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )
    response = client.get(f"/apply/{app.id}/review")
    body = response.get_data(as_text=True)
    assert "not yet complete" in body
    # Submit button must NOT appear when pages are incomplete.
    assert "submit-application" not in body


def test_submit_transitions_complete_draft_to_submitted(
    client, applicant, seeded_ehcf, db
):
    app = _start_application(client, applicant, seeded_ehcf)
    _fill_all_pages(client, app.id)

    response = client.post(f"/apply/{app.id}/submit", follow_redirects=False)
    assert response.status_code == 302
    assert f"/apply/{app.id}/review" in response.headers["Location"]

    db.session.refresh(app)
    assert app.status == ApplicationStatus.SUBMITTED
    assert app.submitted_at is not None


def test_submit_rejects_incomplete_application(
    client, applicant, seeded_ehcf, db
):
    app = _start_application(client, applicant, seeded_ehcf)
    # Only fill the first page.
    client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "12345",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )

    response = client.post(f"/apply/{app.id}/submit", follow_redirects=False)
    assert response.status_code == 302
    assert f"/apply/{app.id}/review" in response.headers["Location"]

    db.session.refresh(app)
    assert app.status == ApplicationStatus.DRAFT
    assert app.submitted_at is None


def test_submit_on_already_submitted_is_a_noop(
    client, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    from datetime import UTC, datetime

    submitted_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    app = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
        submitted_at=submitted_at,
    )
    db.session.add(app)
    db.session.commit()
    _login(client, applicant)

    response = client.post(f"/apply/{app.id}/submit", follow_redirects=False)
    assert response.status_code == 302
    db.session.refresh(app)
    # SQLite strips tzinfo on round-trip; compare the naive timestamps.
    assert app.submitted_at.replace(tzinfo=None) == submitted_at.replace(tzinfo=None)
    assert app.status == ApplicationStatus.SUBMITTED


def test_review_404s_for_other_orgs_application(
    client, other_org_applicant, applicant, seeded_ehcf, db
):
    grant, _form = seeded_ehcf
    app = Application(
        org_id=applicant.org_id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.DRAFT,
    )
    db.session.add(app)
    db.session.commit()

    _login(client, other_org_applicant)
    response = client.get(f"/apply/{app.id}/review")
    assert response.status_code == 404


def test_submitted_review_page_shows_confirmation_panel(
    client, applicant, seeded_ehcf, db
):
    app = _start_application(client, applicant, seeded_ehcf)
    _fill_all_pages(client, app.id)
    client.post(f"/apply/{app.id}/submit")

    response = client.get(f"/apply/{app.id}/review")
    body = response.get_data(as_text=True)
    assert "Application submitted" in body
    assert "govuk-panel" in body
    # No submit button after submission.
    assert "submit-application" not in body


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_ehcf_with_eligibility(seeded_ehcf, db):
    """Extend the standard EHCF fixture to also seed the eligibility form."""
    grant, app_form = seeded_ehcf
    elig_schema = json.loads((FORMS_DIR / "ehcf-eligibility-v1.json").read_text())
    elig_form = Form(
        grant=grant,
        kind=FormKind.ELIGIBILITY,
        version=int(elig_schema.get("version", 1)),
        schema_json=elig_schema,
    )
    db.session.add(elig_form)
    db.session.commit()
    return grant, app_form, elig_form


# Valid eligible answers — matches EHCF eligibility rules exactly.
_ELIGIBLE_ANSWERS = {
    "org_type": "charity",
    "operates_in_england": "true",
    "annual_income": "500000",
    "years_serving_homeless": "5",
    "la_endorsement": "true",
}


def test_eligibility_page_renders(
    client, applicant, seeded_ehcf_with_eligibility
):
    _login(client, applicant)
    response = client.get("/apply/ehcf/eligibility")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Check your eligibility" in body


def test_eligibility_pass_shows_success(
    client, applicant, seeded_ehcf_with_eligibility
):
    _login(client, applicant)
    response = client.post(
        "/apply/ehcf/eligibility",
        data=_ELIGIBLE_ANSWERS,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "You appear to be eligible" in body


def test_eligibility_fail_shows_failure(
    client, applicant, seeded_ehcf_with_eligibility
):
    _login(client, applicant)
    # annual_income exceeds the £5M cap
    data = {**_ELIGIBLE_ANSWERS, "annual_income": "6000000"}
    response = client.post("/apply/ehcf/eligibility", data=data)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "does not appear to be eligible" in body


def test_eligibility_validation_errors(
    client, applicant, seeded_ehcf_with_eligibility
):
    _login(client, applicant)
    # POST an empty form — all required fields are missing.
    response = client.post("/apply/ehcf/eligibility", data={})
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "There is a problem" in body


def test_eligibility_skips_when_no_form(client, applicant, seeded_ehcf):
    """If a grant has no eligibility form, the route redirects to start()."""
    _login(client, applicant)
    response = client.get("/apply/ehcf/eligibility", follow_redirects=False)
    assert response.status_code == 302
    assert "/apply/ehcf/start" in response.headers["Location"]


def test_eligibility_404s_on_unknown_grant(client, applicant):
    _login(client, applicant)
    response = client.get("/apply/no-such-grant/eligibility")
    assert response.status_code == 404
