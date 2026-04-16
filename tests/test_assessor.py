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
# Tests: Monitoring plan
# ---------------------------------------------------------------------------


def test_monitoring_page_renders(client, assessor, submitted_app, assessment):
    """GET monitoring page returns 200."""
    _login(client)
    resp = client.get(f"/assess/{submitted_app.id}/monitoring")
    assert resp.status_code == 200
    assert b"Monitoring plan" in resp.data
    assert b"Generate monitoring plan" in resp.data


def test_monitoring_generate_stores_plan(client, assessor, submitted_app, assessment):
    """POST to monitoring stores the AI-generated plan in notes_json."""
    _login(client)

    fake_plan = {
        "kpis": [
            {
                "name": "People supported",
                "definition": "Number of individuals receiving support",
                "target": "200 per year",
                "baseline": "0",
                "evidence_source": "Case management system",
                "reporting_frequency": "quarterly",
                "owner": "Project manager",
            }
        ],
        "milestones": [
            {
                "period": "Month 1-3",
                "description": "Recruit staff and set up services",
                "evidence_required": "Signed contracts and induction records",
            }
        ],
        "risk_review_points": ["Month 6", "Month 12", "Month 24"],
        "summary": "A comprehensive monitoring plan for homelessness support.",
    }

    # Mock the AI call at the module level in assessor
    from unittest.mock import patch
    with patch("app.assessor._call_claude_for_monitoring", return_value=fake_plan):
        resp = client.post(
            f"/assess/{submitted_app.id}/monitoring",
            follow_redirects=True,
        )

    assert resp.status_code == 200
    _db.session.refresh(assessment)
    stored_plan = assessment.notes_json.get("_monitoring_plan")
    assert stored_plan is not None
    assert stored_plan["kpis"][0]["name"] == "People supported"
    assert stored_plan["summary"] == "A comprehensive monitoring plan for homelessness support."


def test_monitoring_page_shows_kpis(client, assessor, submitted_app, assessment):
    """After generating a plan, the monitoring page displays the KPI table."""
    _login(client)

    # Pre-populate a monitoring plan directly
    assessment.notes_json = {
        "_monitoring_plan": {
            "kpis": [
                {
                    "name": "Rough sleepers housed",
                    "definition": "People moved into settled accommodation",
                    "target": "50 per year",
                    "baseline": "0",
                    "evidence_source": "Housing records",
                    "reporting_frequency": "quarterly",
                    "owner": "Housing lead",
                }
            ],
            "milestones": [
                {
                    "period": "Month 1-3",
                    "description": "Set up referral pathways",
                    "evidence_required": "Partnership agreements",
                }
            ],
            "risk_review_points": ["Month 6", "Month 12"],
            "summary": "Monitoring framework for housing support.",
        }
    }
    _db.session.commit()

    resp = client.get(f"/assess/{submitted_app.id}/monitoring")
    assert resp.status_code == 200
    assert b"Rough sleepers housed" in resp.data
    assert b"Housing records" in resp.data
    assert b"Set up referral pathways" in resp.data
    assert b"Month 6" in resp.data
    assert b"Regenerate monitoring plan" in resp.data
