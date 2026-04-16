"""Shared pytest fixtures for the grants platform."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Grant, GrantStatus


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
