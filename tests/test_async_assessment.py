"""Tests for the async AI assessment pipeline.

Covers the contract introduced by ``app/tasks.py`` + :func:`queue_assessment`:

* submission returns fast (the applicant isn't blocked on Claude)
* lifecycle transitions: no row → PENDING → COMPLETED (happy path)
* failures persist a FAILED row with an error message (not a missing row)
* retry via :func:`queue_assessment` resets a FAILED row in place
* COMPLETED / PENDING rows are idempotent — no double-enqueue
* the background runner itself runs tasks with a fresh app context

Tests run with ``TASKS_SYNC`` (set implicitly by ``TestConfig.TESTING = True``)
so the pool runs inline — we assert on the post-run state directly rather
than polling.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.models import (
    Application,
    ApplicationStatus,
    Assessment,
    AssessmentRecommendation,
    AssessmentStatus,
    Grant,
    GrantStatus,
    Organisation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def grant(db):
    g = Grant(
        slug="async-test",
        name="Async Test Grant",
        status=GrantStatus.OPEN,
        config_json={
            "slug": "async-test",
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
                    "auto_reject_on_zero": True,
                },
            ],
        },
    )
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture()
def org(db):
    o = Organisation(name="Async Test Org", contact_email="async@test.local")
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
        answers_json={"organisation": {"name": "Async Test Org"}},
    )
    db.session.add(app)
    db.session.commit()
    return app


def _good_response(scores=None, recommendation="fund"):
    payload = json.dumps(
        {
            "scores": scores or {"skills": 2, "proposal": 2},
            "notes": {"skills": "Solid.", "proposal": "Clear."},
            "gap_analysis": "Reasonable proposal.",
            "recommendation": recommendation,
        }
    )
    message = MagicMock()
    message.content = [MagicMock(text=payload)]
    return message


# ---------------------------------------------------------------------------
# queue_assessment — preconditions
# ---------------------------------------------------------------------------


def test_queue_assessment_without_api_key_returns_none(app, submitted_application):
    """No key set → queue is a no-op. Matches the pre-async 'silent skip'
    behaviour that existing submit integration tests rely on."""
    with app.app_context():
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from app.assessor_ai import queue_assessment

            result = queue_assessment(submitted_application.id)

        assert result is None
        assert Assessment.query.count() == 0


def test_queue_assessment_missing_application_returns_none(app):
    with app.app_context(), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        from app.assessor_ai import queue_assessment

        assert queue_assessment(99999) is None


def test_queue_assessment_grant_without_criteria_returns_none(app, db, org):
    empty_grant = Grant(
        slug="empty",
        name="Empty",
        status=GrantStatus.OPEN,
        config_json={"slug": "empty", "criteria": []},
    )
    db.session.add(empty_grant)
    db.session.flush()
    application = Application(
        org_id=org.id,
        grant_id=empty_grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
        answers_json={},
    )
    db.session.add(application)
    db.session.commit()

    with app.app_context():
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            from app.assessor_ai import queue_assessment

            assert queue_assessment(application.id) is None
        assert Assessment.query.count() == 0


# ---------------------------------------------------------------------------
# queue_assessment — happy path + idempotency
# ---------------------------------------------------------------------------


def test_queue_assessment_transitions_pending_to_completed(app, submitted_application):
    """With TASKS_SYNC, the worker runs inline — the returned row has already
    transitioned to COMPLETED by the time queue_assessment returns."""
    with app.app_context():
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic") as mock_anthropic_cls,
        ):
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = _good_response()

            from app.assessor_ai import queue_assessment

            assessment = queue_assessment(submitted_application.id)

        # The row was created and then the sync worker filled it in.
        assert assessment is not None
        from app.extensions import db as _db

        _db.session.refresh(assessment)
        assert assessment.status == AssessmentStatus.COMPLETED
        assert assessment.started_at is not None
        assert assessment.completed_at is not None
        assert assessment.weighted_total == (2 * 50) + (2 * 50)
        assert assessment.recommendation == AssessmentRecommendation.FUND
        assert assessment.error_message is None


def test_queue_assessment_is_idempotent_for_completed_rows(app, submitted_application):
    with app.app_context():
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic") as mock_anthropic_cls,
        ):
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = _good_response()

            from app.assessor_ai import queue_assessment

            first = queue_assessment(submitted_application.id)
            second = queue_assessment(submitted_application.id)

        # Only one Claude call — the second queue saw a COMPLETED row and bailed.
        assert mock_client.messages.create.call_count == 1
        assert first.id == second.id
        assert Assessment.query.count() == 1


# ---------------------------------------------------------------------------
# Failure + retry
# ---------------------------------------------------------------------------


def test_process_assessment_marks_row_failed_on_api_error(app, submitted_application):
    """Any exception raised inside the worker is caught and persisted on the
    row as status=FAILED with a truncated error_message."""
    with app.app_context():
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic") as mock_anthropic_cls,
        ):
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.side_effect = RuntimeError("network is on fire")

            from app.assessor_ai import queue_assessment

            queue_assessment(submitted_application.id)

        assessment = Assessment.query.filter_by(application_id=submitted_application.id).first()
        assert assessment is not None
        assert assessment.status == AssessmentStatus.FAILED
        assert "network is on fire" in (assessment.error_message or "")
        assert assessment.scores_json == {}
        assert assessment.completed_at is not None  # we stamp the failure time too


def test_queue_assessment_retries_failed_row_in_place(app, submitted_application):
    """Calling queue_assessment on a FAILED row resets it and requeues. The
    assessor's 'Retry AI' button relies on this path."""
    with app.app_context():
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic") as mock_anthropic_cls,
        ):
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            # First call fails.
            mock_client.messages.create.side_effect = RuntimeError("boom")

            from app.assessor_ai import queue_assessment

            first = queue_assessment(submitted_application.id)

            # Second call succeeds.
            mock_client.messages.create.side_effect = None
            mock_client.messages.create.return_value = _good_response()
            second = queue_assessment(submitted_application.id)

        from app.extensions import db as _db

        _db.session.refresh(second)
        assert first.id == second.id  # same row, not a new one
        assert second.status == AssessmentStatus.COMPLETED
        assert second.error_message is None
        assert second.weighted_total == (2 * 50) + (2 * 50)
        # Ensure only one Assessment row exists.
        assert Assessment.query.count() == 1


def test_queue_assessment_skips_pending_row(app, submitted_application, db):
    """If a PENDING row already exists (e.g. another request just queued it)
    we must not enqueue a second worker — the first one will complete or fail
    on its own timeline."""
    from app.assessor_ai import _get_or_create_ai_user

    with app.app_context():
        ai_user = _get_or_create_ai_user()
        existing = Assessment(
            application_id=submitted_application.id,
            assessor_id=ai_user.id,
            scores_json={},
            notes_json={},
            status=AssessmentStatus.PENDING,
        )
        db.session.add(existing)
        db.session.commit()

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic") as mock_anthropic_cls,
        ):
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client

            from app.assessor_ai import queue_assessment

            result = queue_assessment(submitted_application.id)

        assert result.id == existing.id
        assert mock_client.messages.create.call_count == 0
        db.session.refresh(existing)
        assert existing.status == AssessmentStatus.PENDING


# ---------------------------------------------------------------------------
# Submission integration — applicant.submit must not run Claude inline
# ---------------------------------------------------------------------------


def test_submit_enqueues_assessment_and_returns_fast(client, applicant_user, seeded_grant, db):
    """End-to-end: hitting /apply/<id>/submit must call queue_assessment, not
    the old sync path, so the response returns as soon as the PENDING row is
    written."""
    # Seed a form matching the grant so the submit handler can load it.
    from app.models import Form, FormKind

    form = Form(
        grant_id=seeded_grant.id,
        kind=FormKind.APPLICATION,
        version=1,
        schema_json={"id": "async", "version": 1, "pages": []},
    )
    db.session.add(form)
    db.session.flush()

    application = Application(
        org_id=applicant_user.org_id,
        grant_id=seeded_grant.id,
        form_version=1,
        status=ApplicationStatus.DRAFT,
        answers_json={},
    )
    db.session.add(application)
    db.session.commit()

    # Log in as the applicant.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(applicant_user.id)
        sess["_fresh"] = True

    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        patch("app.assessor_ai.queue_assessment") as mock_queue,
    ):
        response = client.post(f"/apply/{application.id}/submit")

    # The handler always delegates to queue_assessment — never to the old
    # assess_application sync path.
    assert mock_queue.called
    (called_app_id,), _ = mock_queue.call_args
    assert called_app_id == application.id
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# app.tasks — generic runner
# ---------------------------------------------------------------------------


def test_run_in_background_sync_mode_runs_inline(app):
    """With TESTING=True the runner executes the callable synchronously,
    pushing an app context around it so db / current_app are available."""
    from flask import current_app

    from app.tasks import run_in_background

    seen = {}

    def _task(n: int) -> None:
        seen["n"] = n
        seen["app_name"] = current_app.name

    run_in_background(app, _task, 42)

    assert seen == {"n": 42, "app_name": app.name}


def test_run_in_background_swallows_exceptions(app):
    """Exceptions in a background task never propagate back to the caller —
    the submit handler has long since returned when a task fails."""
    from app.tasks import run_in_background

    def _explode() -> None:
        raise RuntimeError("nope")

    # Should not raise.
    run_in_background(app, _explode)
