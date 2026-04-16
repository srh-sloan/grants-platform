"""Shared pytest fixtures for the grants platform."""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
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


@pytest.fixture()
def app():
    app = create_app("config.TestConfig")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seeded_grant(db):
    grant = Grant(
        slug="ehcf",
        name="Ending Homelessness in Communities Fund",
        status=GrantStatus.OPEN,
        config_json={
            "slug": "ehcf",
            "summary": "Test summary",
            "criteria": [
                {"id": "skills", "label": "Skills", "weight": 100, "max": 3, "auto_reject_on_zero": True}
            ],
        },
    )
    db.session.add(grant)
    db.session.commit()
    return grant


@pytest.fixture()
def applicant_user(db, seeded_grant):
    """Create an applicant user with an organisation."""
    org = Organisation(
        name="Test Org",
        contact_name="Test Contact",
        contact_email="test@example.com",
    )
    db.session.add(org)
    db.session.flush()
    user = User(
        email="applicant@test.com",
        password_hash=generate_password_hash("TestPass1!"),
        role=UserRole.APPLICANT,
        org_id=org.id,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def assessor_user(db):
    """Create an assessor user."""
    user = User(
        email="assessor@test.com",
        password_hash=generate_password_hash("TestPass1!"),
        role=UserRole.ASSESSOR,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def submitted_application(db, seeded_grant, applicant_user):
    """Create a submitted application with sample answers."""
    form = Form(
        grant_id=seeded_grant.id,
        kind=FormKind.APPLICATION,
        version=1,
        schema_json={"id": "test", "version": 1, "pages": []},
    )
    db.session.add(form)
    db.session.flush()
    application = Application(
        org_id=applicant_user.org_id,
        grant_id=seeded_grant.id,
        form_version=1,
        status=ApplicationStatus.SUBMITTED,
        answers_json={"organisation": {"name": "Test Org"}},
    )
    db.session.add(application)
    db.session.commit()
    return application
