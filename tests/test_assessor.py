"""Tests for assessor routes — multi-stage assessment gates.

Covers the eligibility gate, scored evaluation preservation, declaration
gate, and decision-recording flow enforcement added in P4.5.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models import (
    Application,
    ApplicationStatus,
    Assessment,
    AssessmentRecommendation,
    Form,
    FormKind,
    Grant,
    GrantStatus,
    Organisation,
    User,
    UserRole,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    from app import create_app

    app = create_app("config.TestConfig")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def grant(app):
    g = Grant(
        slug="ehcf",
        name="EHCF",
        status=GrantStatus.OPEN,
        config_json={
            "criteria": [
                {
                    "id": "skills",
                    "label": "Skills",
                    "weight": 50,
                    "max": 3,
                    "auto_reject_on_zero": True,
                },
                {
                    "id": "proposal",
                    "label": "Proposal",
                    "weight": 50,
                    "max": 3,
                    "auto_reject_on_zero": False,
                },
            ],
            "eligibility": [
                {
                    "id": "org_type",
                    "type": "in",
                    "label": "Organisation type",
                    "values": ["charity", "CIO"],
                },
            ],
        },
    )
    _db.session.add(g)
    _db.session.commit()
    return g


@pytest.fixture()
def assessor(app):
    u = User(
        email="assessor@test.com",
        password_hash=generate_password_hash("TestPass1!"),
        role=UserRole.ASSESSOR,
    )
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def submitted_app(grant, assessor):
    """Submitted application with an org."""
    org = Organisation(name="Test Org", contact_email="org@test.com")
    _db.session.add(org)
    _db.session.flush()
    form = Form(
        grant_id=grant.id,
        kind=FormKind.APPLICATION,
        version=1,
        schema_json={"id": "test", "version": 1, "pages": []},
    )
    _db.session.add(form)
    _db.session.flush()
    application = Application(
        org_id=org.id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
        answers_json={"organisation": {"name": "Test Org"}},
    )
    _db.session.add(application)
    _db.session.commit()
    return application


@pytest.fixture()
def assessment(submitted_app, assessor):
    """Pre-create an Assessment so _get_or_create_assessment finds it
    without importing assessor_ai (which requires the anthropic SDK)."""
    a = Assessment(
        application_id=submitted_app.id,
        assessor_id=assessor.id,
        scores_json={},
        notes_json={},
    )
    _db.session.add(a)
    _db.session.commit()
    return a


def _login(client, email: str = "assessor@test.com", password: str = "TestPass1!"):
    """Log in the assessor via the auth blueprint."""
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Tests: Eligibility gate
# ---------------------------------------------------------------------------


def test_eligibility_gate_saves(client, assessor, submitted_app, assessment):
    """POST to eligibility-gate saves _eligibility_passed in scores_json."""
    _login(client)
    resp = client.post(
        f"/assess/{submitted_app.id}/eligibility-gate",
        data={
            "eligibility_passed": "true",
            "eligibility_notes": "All criteria verified.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    _db.session.refresh(assessment)
    assert assessment.scores_json["_eligibility_passed"] is True
    assert assessment.notes_json["_eligibility_notes"] == "All criteria verified."


def test_eligibility_gate_fail_saves(client, assessor, submitted_app, assessment):
    """POST to eligibility-gate with fail saves _eligibility_passed=False."""
    _login(client)
    resp = client.post(
        f"/assess/{submitted_app.id}/eligibility-gate",
        data={
            "eligibility_passed": "false",
            "eligibility_notes": "Income too high.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    _db.session.refresh(assessment)
    assert assessment.scores_json["_eligibility_passed"] is False


def test_eligibility_gate_requires_notes(client, assessor, submitted_app, assessment):
    """Eligibility gate rejects when notes are missing."""
    _login(client)
    resp = client.post(
        f"/assess/{submitted_app.id}/eligibility-gate",
        data={"eligibility_passed": "true", "eligibility_notes": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    _db.session.refresh(assessment)
    # Gate key should not be set
    assert assessment.scores_json.get("_eligibility_passed") is None


# ---------------------------------------------------------------------------
# Tests: Declaration gate
# ---------------------------------------------------------------------------


def test_declaration_gate_saves(client, assessor, submitted_app, assessment):
    """POST to declaration-gate saves _declaration_passed in scores_json."""
    _login(client)
    resp = client.post(
        f"/assess/{submitted_app.id}/declaration-gate",
        data={
            "declaration_passed": "true",
            "declaration_notes": "No conflicts of interest.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    _db.session.refresh(assessment)
    assert assessment.scores_json["_declaration_passed"] is True
    assert assessment.notes_json["_declaration_notes"] == "No conflicts of interest."


# ---------------------------------------------------------------------------
# Tests: Decision flow enforcement
# ---------------------------------------------------------------------------


def test_decision_blocked_without_eligibility(client, assessor, submitted_app, assessment):
    """Attempting to record a decision without eligibility gate returns error."""
    _login(client)
    resp = client.post(
        f"/assess/{submitted_app.id}/decision",
        data={
            "recommendation": "fund",
            "decision_notes": "Looks good.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Should see the error message about completing eligibility
    assert b"eligibility" in resp.data.lower()
    # Application status should remain submitted (not approved)
    _db.session.refresh(submitted_app)
    assert submitted_app.status == ApplicationStatus.SUBMITTED


def test_eligibility_fail_allows_reject(client, assessor, submitted_app, assessment):
    """After eligibility failure, assessor can immediately reject."""
    _login(client)

    # Step 1: Fail eligibility
    client.post(
        f"/assess/{submitted_app.id}/eligibility-gate",
        data={
            "eligibility_passed": "false",
            "eligibility_notes": "Organisation type not eligible.",
        },
    )

    # Step 2: Record reject decision (should succeed without scoring or declaration)
    resp = client.post(
        f"/assess/{submitted_app.id}/decision",
        data={
            "recommendation": "reject",
            "decision_notes": "Failed eligibility — not a qualifying organisation.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    _db.session.refresh(submitted_app)
    assert submitted_app.status == ApplicationStatus.REJECTED


def test_eligibility_fail_blocks_fund(client, assessor, submitted_app, assessment):
    """After eligibility failure, assessor cannot fund — only reject."""
    _login(client)

    # Step 1: Fail eligibility
    client.post(
        f"/assess/{submitted_app.id}/eligibility-gate",
        data={
            "eligibility_passed": "false",
            "eligibility_notes": "Income exceeded.",
        },
    )

    # Step 2: Try to fund — should be blocked
    resp = client.post(
        f"/assess/{submitted_app.id}/decision",
        data={
            "recommendation": "fund",
            "decision_notes": "Attempted fund after elig fail.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    _db.session.refresh(submitted_app)
    # Should still be submitted, not approved
    assert submitted_app.status == ApplicationStatus.SUBMITTED


def test_full_happy_path(client, assessor, submitted_app, assessment):
    """Full flow: eligibility pass -> score -> declaration pass -> decision."""
    _login(client)
    app_id = submitted_app.id

    # 1. Pass eligibility
    client.post(
        f"/assess/{app_id}/eligibility-gate",
        data={
            "eligibility_passed": "true",
            "eligibility_notes": "All criteria met.",
        },
    )

    # 2. Score all criteria
    client.post(
        f"/assess/{app_id}/score",
        data={
            "score_skills": "3",
            "notes_skills": "Excellent track record.",
            "score_proposal": "2",
            "notes_proposal": "Solid but room for improvement.",
        },
    )

    # 3. Pass declaration
    client.post(
        f"/assess/{app_id}/declaration-gate",
        data={
            "declaration_passed": "true",
            "declaration_notes": "No conflicts.",
        },
    )

    # 4. Record decision
    resp = client.post(
        f"/assess/{app_id}/decision",
        data={
            "recommendation": "fund",
            "decision_notes": "Strong application.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    _db.session.refresh(submitted_app)
    assert submitted_app.status == ApplicationStatus.APPROVED

    _db.session.refresh(assessment)
    assert assessment.recommendation == AssessmentRecommendation.FUND
    assert assessment.completed_at is not None


def test_decision_blocked_without_declaration(client, assessor, submitted_app, assessment):
    """Decision is blocked when eligibility passes and scoring is done but declaration is missing."""
    _login(client)
    app_id = submitted_app.id

    # 1. Pass eligibility
    client.post(
        f"/assess/{app_id}/eligibility-gate",
        data={
            "eligibility_passed": "true",
            "eligibility_notes": "OK.",
        },
    )

    # 2. Score all criteria
    client.post(
        f"/assess/{app_id}/score",
        data={
            "score_skills": "2",
            "notes_skills": "Good.",
            "score_proposal": "2",
            "notes_proposal": "Good.",
        },
    )

    # 3. Skip declaration and try to decide
    resp = client.post(
        f"/assess/{app_id}/decision",
        data={
            "recommendation": "fund",
            "decision_notes": "Try to decide.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"declaration" in resp.data.lower()
    _db.session.refresh(submitted_app)
    assert submitted_app.status == ApplicationStatus.SUBMITTED


# ---------------------------------------------------------------------------
# Tests: application detail back-link context
# ---------------------------------------------------------------------------


def test_detail_back_link_defaults_to_queue(client, assessor, submitted_app, assessment):
    """With no return_to, the detail page back-link points at the queue."""
    _login(client)
    resp = client.get(f"/assess/{submitted_app.id}")
    assert resp.status_code == 200
    assert b"Back to queue" in resp.data
    assert b"Back to allocation dashboard" not in resp.data


def test_detail_back_link_follows_return_to_allocation(
    client, assessor, submitted_app, assessment
):
    """return_to=allocation switches the back-link to the allocation dashboard."""
    _login(client)
    resp = client.get(f"/assess/{submitted_app.id}?return_to=allocation")
    assert resp.status_code == 200
    assert b"Back to allocation dashboard" in resp.data
    assert b"Back to queue" not in resp.data


def test_detail_back_link_ignores_unknown_return_to(
    client, assessor, submitted_app, assessment
):
    """An unrecognised return_to value falls back to the queue link."""
    _login(client)
    resp = client.get(f"/assess/{submitted_app.id}?return_to=../evil")
    assert resp.status_code == 200
    assert b"Back to queue" in resp.data
    assert b"Back to allocation dashboard" not in resp.data


def test_detail_return_to_preserved_across_post_redirect(
    client, assessor, submitted_app, assessment
):
    """POST handlers preserve return_to when redirecting back to the detail view."""
    _login(client)
    # Post the eligibility gate with a hidden return_to=allocation, mimicking
    # the form the template renders when the user arrived from allocation.
    resp = client.post(
        f"/assess/{submitted_app.id}/eligibility-gate",
        data={
            "eligibility_passed": "true",
            "eligibility_notes": "All checks OK.",
            "return_to": "allocation",
        },
    )
    # 302 redirect preserves the query string.
    assert resp.status_code == 302
    assert "return_to=allocation" in resp.headers["Location"]


def test_allocation_review_link_threads_return_to(
    client, assessor, submitted_app, assessment
):
    """The allocation dashboard Review link carries return_to=allocation."""
    _login(client)
    # Give the assessment a weighted_total so the allocation query returns it.
    assessment.weighted_total = 100
    _db.session.commit()

    resp = client.get("/assess/allocation")
    assert resp.status_code == 200
    assert f"/assess/{submitted_app.id}?return_to=allocation".encode() in resp.data
