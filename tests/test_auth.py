"""Tests for the auth blueprint — login, register, logout, role gating.

Stream A owns this module. Tests are deliberately hermetic: no reliance on
Stream D's shared fixtures so this file can be read (and run) without waiting
for them to land.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db as _db
from app.models import Organisation, User, UserRole

# ---------------------------------------------------------------------------
# Local fixtures (kept out of conftest.py — Stream D owns that)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_user(db):
    """Factory for creating users with a password. Returns (user, raw_password)."""
    created = []

    def _make(
        *,
        email: str = "applicant@example.test",
        password: str = "correct-horse-battery-staple",
        role: UserRole = UserRole.APPLICANT,
        organisation_name: str = "Test Org",
        with_org: bool = True,
    ):
        org = None
        if with_org:
            org = Organisation(name=organisation_name, contact_email=email)
            _db.session.add(org)
            _db.session.flush()
        user = User(
            email=email.lower(),
            password_hash=generate_password_hash(password),
            role=role,
            org_id=org.id if org else None,
        )
        _db.session.add(user)
        _db.session.commit()
        created.append(user.id)
        return user, password

    yield _make


# ---------------------------------------------------------------------------
# GET rendering
# ---------------------------------------------------------------------------


def test_login_page_renders(client):
    response = client.get("/auth/login")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Sign in" in body
    assert 'name="email"' in body
    assert 'name="password"' in body


def test_register_page_renders(client):
    response = client.get("/auth/register")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Create an account" in body
    assert 'name="organisation_name"' in body
    assert 'name="confirm_password"' in body


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_creates_applicant_and_logs_in(client, db):
    response = client.post(
        "/auth/register",
        data={
            "organisation_name": "Shelter Bristol",
            "email": "lead@shelterbristol.test",
            "password": "a-valid-password",
            "confirm_password": "a-valid-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/apply/")

    user = db.session.execute(
        select(User).where(User.email == "lead@shelterbristol.test")
    ).scalar_one()
    assert user.role == UserRole.APPLICANT
    assert user.organisation is not None
    assert user.organisation.name == "Shelter Bristol"
    assert check_password_hash(user.password_hash, "a-valid-password")
    # Password is hashed, not stored as plaintext.
    assert "a-valid-password" not in user.password_hash

    # Subsequent request confirms the session cookie was set.
    dash = client.get("/apply/")
    assert dash.status_code == 200
    assert "Your applications" in dash.get_data(as_text=True)


def test_register_normalises_email_to_lowercase(client, db):
    client.post(
        "/auth/register",
        data={
            "organisation_name": "Shout Out",
            "email": "MiXeD@Example.Test",
            "password": "a-valid-password",
            "confirm_password": "a-valid-password",
        },
    )
    user = db.session.execute(
        select(User).where(User.email == "mixed@example.test")
    ).scalar_one()
    assert user.email == "mixed@example.test"


def test_register_rejects_mismatched_passwords(client, db):
    response = client.post(
        "/auth/register",
        data={
            "organisation_name": "Shelter",
            "email": "a@b.test",
            "password": "a-valid-password",
            "confirm_password": "different-password",
        },
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Passwords must match" in body
    assert db.session.execute(select(User)).scalars().all() == []


def test_register_rejects_short_password(client, db):
    response = client.post(
        "/auth/register",
        data={
            "organisation_name": "X",
            "email": "short@x.test",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 200
    assert "at least 10 characters" in response.get_data(as_text=True)


def test_register_rejects_bad_email(client):
    response = client.post(
        "/auth/register",
        data={
            "organisation_name": "X",
            "email": "not-an-email",
            "password": "a-valid-password",
            "confirm_password": "a-valid-password",
        },
    )
    assert response.status_code == 200
    assert "correct format" in response.get_data(as_text=True)


def test_register_rejects_duplicate_email(client, db, make_user):
    make_user(email="dup@x.test")
    response = client.post(
        "/auth/register",
        data={
            "organisation_name": "Another Org",
            "email": "dup@x.test",
            "password": "a-valid-password",
            "confirm_password": "a-valid-password",
        },
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "already exists" in body


def test_register_strips_whitespace_from_organisation_name(client, db):
    """Leading/trailing whitespace in the org name is trimmed on entry."""
    response = client.post(
        "/auth/register",
        data={
            "organisation_name": "  Shelter Bristol  ",
            "email": "trim@example.test",
            "password": "a-valid-password",
            "confirm_password": "a-valid-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    user = db.session.execute(
        select(User).where(User.email == "trim@example.test")
    ).scalar_one()
    assert user.organisation.name == "Shelter Bristol"


def test_organisation_model_strips_name_and_contact_name(db):
    """The Organisation model trims whitespace regardless of write path."""
    org = Organisation(
        name="  Padded Org  ",
        contact_name="\tAlice Applicant\n",
        contact_email="a@b.test",
    )
    db.session.add(org)
    db.session.commit()

    db.session.refresh(org)
    assert org.name == "Padded Org"
    assert org.contact_name == "Alice Applicant"


def test_dashboard_trims_organisation_name_on_render(client, db, make_user):
    """Legacy/padded org names are rendered clean on the applicant dashboard."""
    user, password = make_user(
        email="dash@example.test", organisation_name="Padded Org"
    )
    # Bypass the validator by patching directly in the DB to simulate legacy
    # data that predates the strip-on-entry fix.
    db.session.execute(
        Organisation.__table__.update()
        .where(Organisation.id == user.org_id)
        .values(name="   Padded Org   ")
    )
    db.session.commit()

    client.post(
        "/auth/login",
        data={"email": "dash@example.test", "password": password},
    )
    response = client.get("/apply/")
    body = response.get_data(as_text=True)
    assert "<strong>Padded Org</strong>" in body
    assert "   Padded Org   " not in body


def test_register_redirects_if_already_logged_in(client, make_user):
    _user, password = make_user(email="al@x.test")
    client.post("/auth/login", data={"email": "al@x.test", "password": password})

    response = client.get("/auth/register", follow_redirects=False)
    assert response.status_code == 302
    assert "/apply/" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_succeeds_with_valid_credentials(client, make_user):
    _user, password = make_user(email="good@x.test")

    response = client.post(
        "/auth/login",
        data={"email": "good@x.test", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/apply/" in response.headers["Location"]


def test_login_is_case_insensitive_on_email(client, make_user):
    _user, password = make_user(email="case@x.test")

    response = client.post(
        "/auth/login",
        data={"email": "CaSe@X.Test", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/apply/" in response.headers["Location"]


def test_login_rejects_wrong_password(client, make_user):
    make_user(email="user@x.test", password="the-right-password")

    response = client.post(
        "/auth/login",
        data={"email": "user@x.test", "password": "wrong"},
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Email or password is incorrect" in body


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/auth/login",
        data={"email": "nobody@nowhere.test", "password": "whatever-123"},
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # Generic error to avoid user enumeration.
    assert "Email or password is incorrect" in body


def test_login_redirects_assessor_to_queue(client, make_user):
    _user, password = make_user(
        email="panel@mhclg.test",
        role=UserRole.ASSESSOR,
        with_org=False,
    )

    response = client.post(
        "/auth/login",
        data={"email": "panel@mhclg.test", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/assess/" in response.headers["Location"]


def test_login_honours_safe_next_param(client, make_user):
    _user, password = make_user(email="next@x.test")

    response = client.post(
        "/auth/login?next=/apply/",
        data={"email": "next@x.test", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/apply/")


def test_login_rejects_open_redirect_in_next(client, make_user):
    _user, password = make_user(email="safe@x.test")

    response = client.post(
        "/auth/login?next=https://evil.example.test/phish",
        data={"email": "safe@x.test", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    # Falls back to role landing, not the attacker-controlled URL.
    assert "evil.example.test" not in response.headers["Location"]
    assert "/apply/" in response.headers["Location"]


def test_login_rejects_protocol_relative_next(client, make_user):
    _user, password = make_user(email="pr@x.test")
    response = client.post(
        "/auth/login?next=//evil.example.test",
        data={"email": "pr@x.test", "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "evil.example.test" not in response.headers["Location"]


def test_login_redirects_already_authenticated(client, make_user):
    _u, password = make_user(email="auth@x.test")
    client.post("/auth/login", data={"email": "auth@x.test", "password": password})

    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout_clears_session_and_redirects(client, make_user):
    _u, password = make_user(email="bye@x.test")
    client.post("/auth/login", data={"email": "bye@x.test", "password": password})

    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    # Dashboard should now bounce to login.
    after = client.get("/apply/", follow_redirects=False)
    assert after.status_code == 302
    assert "/auth/login" in after.headers["Location"]


def test_logout_banner_is_shown_on_landing_page(client, make_user):
    """Flashed confirmation must render on the redirect target (``/``), not the next page."""
    _u, password = make_user(email="flash@x.test")
    client.post("/auth/login", data={"email": "flash@x.test", "password": password})

    response = client.post("/auth/logout", follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "You have been signed out." in body


def test_logout_requires_authentication(client):
    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_logout_is_not_reachable_via_get(client):
    response = client.get("/auth/logout")
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# Role gating
# ---------------------------------------------------------------------------


def test_applicant_cannot_visit_assessor_area(client, make_user):
    _u, password = make_user(email="a@x.test", role=UserRole.APPLICANT)
    client.post("/auth/login", data={"email": "a@x.test", "password": password})

    response = client.get("/assess/")
    assert response.status_code == 403
    assert "You do not have access" in response.get_data(as_text=True)


def test_assessor_cannot_visit_applicant_area(client, make_user):
    _u, password = make_user(
        email="b@x.test", role=UserRole.ASSESSOR, with_org=False
    )
    client.post("/auth/login", data={"email": "b@x.test", "password": password})

    response = client.get("/apply/")
    assert response.status_code == 403


def test_anonymous_dashboard_redirects_to_login_with_next(client):
    response = client.get("/apply/", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/auth/login" in location
    assert "next=" in location


def test_login_page_does_not_flash_default_login_message(client):
    """Flask-Login's default ``login_message`` is suppressed so it does not
    render as a banner on the sign-in page itself (where it is redundant)."""
    # Hitting a protected page would, by default, flash "Please log in to
    # access this page." on the subsequent redirect target.
    response = client.get("/apply/", follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Sign in" in body  # confirms we landed on the login page
    assert "Please log in to access this page" not in body


def test_load_user_returns_user_by_id(app, make_user):
    user, _ = make_user(email="loader@x.test")
    from app.auth import load_user

    loaded = load_user(str(user.id))
    assert loaded is not None
    assert loaded.email == "loader@x.test"


def test_load_user_returns_none_for_unknown(app):
    from app.auth import load_user

    assert load_user("9999") is None


def test_load_user_returns_none_for_malformed_id(app):
    """A tampered / legacy session cookie must sign the user out cleanly,
    not raise and surface as a 500."""
    from app.auth import load_user

    assert load_user("not-a-number") is None
    assert load_user("") is None


# ---------------------------------------------------------------------------
# CSRF — flipped on to verify tokens are rendered and required
# ---------------------------------------------------------------------------


def test_login_template_includes_csrf_token_when_enabled():
    """Login form renders a CSRF token when CSRF protection is on (production)."""
    from app import create_app

    class CSRFOnConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SECRET_KEY = "csrf-on-test"
        UPLOAD_FOLDER = "/tmp/csrf-test-uploads"
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(CSRFOnConfig)
    with csrf_app.app_context():
        _db.create_all()
        try:
            response = csrf_app.test_client().get("/auth/login")
            body = response.get_data(as_text=True)
            assert 'name="csrf_token"' in body
        finally:
            _db.session.remove()
            _db.drop_all()


def test_post_without_csrf_token_is_rejected_when_enabled():
    """Production-mode POST without CSRF token returns 400."""
    from app import create_app

    class CSRFOnConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SECRET_KEY = "csrf-on-test"
        UPLOAD_FOLDER = "/tmp/csrf-test-uploads"
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(CSRFOnConfig)
    with csrf_app.app_context():
        _db.create_all()
        try:
            response = csrf_app.test_client().post(
                "/auth/register",
                data={
                    "organisation_name": "X",
                    "email": "x@x.test",
                    "password": "a-valid-password",
                    "confirm_password": "a-valid-password",
                },
            )
            assert response.status_code == 400
        finally:
            _db.session.remove()
            _db.drop_all()
