"""Tests for the AI assessment layer (app/assessor_ai.py).

These tests mock the Anthropic API so they run offline without an API key.
They verify the full assess_application() contract:
  - creates an Assessment row with correct scores/notes/weighted_total/recommendation
  - is idempotent (no duplicate assessments)
  - handles missing applications gracefully
  - handles unparseable Claude responses gracefully
  - enforces auto-reject when any flagged criterion scores 0
  - upserts the AI system user without crashing on repeated calls
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db as _db
from app.models import (
    Application,
    ApplicationStatus,
    Assessment,
    AssessmentRecommendation,
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
def grant(db):
    g = Grant(
        slug="ehcf-test",
        name="Test Grant",
        status=GrantStatus.OPEN,
        config_json={
            "slug": "ehcf-test",
            "criteria": [
                {"id": "skills", "label": "Skills", "weight": 50, "max": 3, "auto_reject_on_zero": True},
                {"id": "proposal", "label": "Proposal", "weight": 50, "max": 3, "auto_reject_on_zero": True},
            ],
        },
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture()
def org(db):
    o = Organisation(name="Test Org", contact_email="applicant@example.com")
    db.session.add(o)
    db.session.commit()
    return o


@pytest.fixture()
def submitted_application(db, grant, org):
    app = Application(
        org_id=org.id,
        grant_id=grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
        answers_json={
            "organisation": {
                "name": "Test Org",
                "years_serving_homeless": "5",
            },
            "proposal": {
                "project_name": "Street support project",
                "local_challenge": "High rough sleeping rates in the area.",
            },
        },
    )
    db.session.add(app)
    db.session.commit()
    return app


def _mock_claude_response(scores: dict, notes: dict, gap: str, recommendation: str) -> MagicMock:
    """Build a mock Anthropic Message that returns valid JSON."""
    payload = json.dumps({
        "scores": scores,
        "notes": notes,
        "gap_analysis": gap,
        "recommendation": recommendation,
    })
    message = MagicMock()
    message.content = [MagicMock(text=payload)]
    return message


# ---------------------------------------------------------------------------
# Core contract tests
# ---------------------------------------------------------------------------


def test_assess_application_creates_assessment(app, submitted_application):
    """Happy path: assess_application writes a complete Assessment row."""
    mock_response = _mock_claude_response(
        scores={"skills": 2, "proposal": 3},
        notes={"skills": "Good track record.", "proposal": "Strong alignment."},
        gap={"_gap_analysis": "Solid overall."},
        recommendation="fund",
    )
    # Fix: gap_analysis should be a string
    mock_response = _mock_claude_response(
        scores={"skills": 2, "proposal": 3},
        notes={"skills": "Good track record.", "proposal": "Strong alignment."},
        gap="Solid overall, strong proposal.",
        recommendation="fund",
    )

    with app.app_context():
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            from app.assessor_ai import assess_application
            result = assess_application(submitted_application.id)

        assert result is not None
        assert result.application_id == submitted_application.id
        assert result.scores_json == {"skills": 2, "proposal": 3}
        assert result.notes_json["skills"] == "Good track record."
        assert result.notes_json["_gap_analysis"] == "Solid overall, strong proposal."
        assert result.weighted_total == (2 * 50) + (3 * 50)  # 250
        assert result.recommendation == AssessmentRecommendation.FUND
        assert result.completed_at is not None


def test_assess_application_is_idempotent(app, submitted_application):
    """Calling assess_application twice returns the existing Assessment unchanged."""
    mock_response = _mock_claude_response(
        scores={"skills": 2, "proposal": 2},
        notes={"skills": "Ok.", "proposal": "Ok."},
        gap="Average.",
        recommendation="refer",
    )

    with app.app_context():
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            from app.assessor_ai import assess_application
            first = assess_application(submitted_application.id)
            second = assess_application(submitted_application.id)

        # Claude must only have been called once
        assert mock_client.messages.create.call_count == 1
        assert first.id == second.id


def test_assess_application_returns_none_for_missing_app(app):
    """Returns None (does not crash) when the application does not exist."""
    with app.app_context():
        with patch("anthropic.Anthropic"):
            from app.assessor_ai import assess_application
            result = assess_application(99999)
        assert result is None


def test_assess_application_handles_bad_json(app, submitted_application):
    """Returns None and logs when Claude returns unparseable output."""
    message = MagicMock()
    message.content = [MagicMock(text="Sorry, I cannot score this application.")]

    with app.app_context():
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = message

            from app.assessor_ai import assess_application
            result = assess_application(submitted_application.id)

        assert result is None
        # Confirm no Assessment row was committed
        assessment = Assessment.query.filter_by(
            application_id=submitted_application.id
        ).first()
        assert assessment is None


def test_assess_application_auto_reject_on_zero(app, submitted_application):
    """Recommendation is forced to REJECT if any auto_reject_on_zero criterion scores 0."""
    mock_response = _mock_claude_response(
        scores={"skills": 0, "proposal": 3},
        notes={"skills": "No evidence.", "proposal": "Strong."},
        gap="Auto-rejected on skills.",
        recommendation="fund",  # Claude says fund, but auto-reject should override
    )

    with app.app_context():
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            from app.assessor_ai import assess_application
            result = assess_application(submitted_application.id)

        assert result is not None
        assert result.recommendation == AssessmentRecommendation.REJECT
        assert result.weighted_total == (0 * 50) + (3 * 50)  # 150


def test_assess_application_upserts_ai_user(app, submitted_application):
    """The synthetic AI assessor user is created if it does not exist."""
    mock_response = _mock_claude_response(
        scores={"skills": 1, "proposal": 1},
        notes={"skills": "Minimal.", "proposal": "Minimal."},
        gap="Weak.",
        recommendation="reject",
    )

    with app.app_context():
        from app.models import User

        # Confirm no AI user exists yet
        ai_user = User.query.filter_by(email="ai-assessor@system.local").first()
        assert ai_user is None

        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            from app.assessor_ai import assess_application
            result = assess_application(submitted_application.id)

        ai_user = User.query.filter_by(email="ai-assessor@system.local").first()
        assert ai_user is not None
        assert ai_user.role == UserRole.ASSESSOR
        assert ai_user.password_hash == "!"  # unusable -- cannot log in


def test_assess_application_strips_markdown_fences(app, submitted_application):
    """Handles Claude wrapping output in code fences (```json ... ```)."""
    payload = json.dumps({
        "scores": {"skills": 2, "proposal": 2},
        "notes": {"skills": "Fine.", "proposal": "Fine."},
        "gap_analysis": "Adequate.",
        "recommendation": "fund",
    })
    message = MagicMock()
    message.content = [MagicMock(text="```json\n" + payload + "\n```")]

    with app.app_context():
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = message

            from app.assessor_ai import assess_application
            result = assess_application(submitted_application.id)

        assert result is not None
        assert result.scores_json == {"skills": 2, "proposal": 2}


def test_assess_application_no_criteria(app, db, org):
    """Returns None when the grant has no criteria defined."""
    grant_no_criteria = Grant(
        slug="empty-grant",
        name="Empty Grant",
        status=GrantStatus.OPEN,
        config_json={"slug": "empty-grant", "criteria": []},
    )
    db.session.add(grant_no_criteria)
    db.session.flush()

    application = Application(
        org_id=org.id,
        grant_id=grant_no_criteria.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
        answers_json={},
    )
    db.session.add(application)
    db.session.commit()

    with app.app_context():
        with patch("anthropic.Anthropic"):
            from app.assessor_ai import assess_application
            result = assess_application(application.id)

        assert result is None
