"""Integration tests: the applicant blueprint calls external validators on save.

These tests stub out the external registry so we never hit a real network.
The feature-flag default in ``TestConfig`` is off, so we flip it on for this
module to exercise the live code path — keeping the existing applicant
tests unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db as _db
from app.external_validators import (
    FindThatCharityValidator,
    get_validator,
    register_validator,
)
from app.models import (
    Application,
    Form,
    FormKind,
    Grant,
    GrantStatus,
    Organisation,
    User,
    UserRole,
)

FORMS_DIR = Path(__file__).resolve().parent.parent / "app" / "forms"
GRANTS_DIR = Path(__file__).resolve().parent.parent / "seed" / "grants"


# ---------------------------------------------------------------------------
# Test harness: app with external validation enabled + fake fetcher
# ---------------------------------------------------------------------------


class _TestConfigWithExternalValidation:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    UPLOAD_FOLDER = str(Path(__file__).resolve().parent / "_uploads")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    EXTERNAL_VALIDATORS_ENABLED = True  # the switch under test
    COMPANIES_HOUSE_API_KEY = None  # keep CH validator in "skipped" mode
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class _FakeFetcher:
    """Replay a URL → response map; any unknown URL is a 404."""

    def __init__(self, responses: dict[str, object]):
        self._responses = responses

    def __call__(self, url, timeout, *, headers=None):
        value = self._responses.get(url)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def app_with_external_validation():
    app = create_app(_TestConfigWithExternalValidation)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app_with_external_validation):
    return app_with_external_validation.test_client()


@pytest.fixture(autouse=True)
def _restore_find_that_charity_validator():
    """Snapshot the default FindThatCharity validator and restore it after each test.

    Tests swap in stubs with controlled fetchers; we put the real one back
    so subsequent test modules (or a test order shuffle) see a clean slate.
    """
    original = get_validator("find_that_charity")
    yield
    if original is not None:
        register_validator(original)


@pytest.fixture
def stub_charity_hit():
    """Register a FindThatCharity validator whose fetcher returns a known hit."""
    fetcher = _FakeFetcher(
        {"https://ftc.test/charity/1234567.json": {"name": "Shelter Bristol Trust"}}
    )
    register_validator(FindThatCharityValidator(fetcher=fetcher, base_url="https://ftc.test"))


@pytest.fixture
def stub_charity_miss():
    """Register a validator whose fetcher returns 404 for every URL."""
    register_validator(
        FindThatCharityValidator(fetcher=_FakeFetcher({}), base_url="https://ftc.test")
    )


@pytest.fixture
def stub_charity_network_error():
    """Register a validator that simulates a provider outage.

    Both the charity and company endpoints error — the validator must
    block with a 'try again' message rather than silently passing.
    """
    from app.external_validators.base import ExternalValidatorError

    fetcher = _FakeFetcher(
        {
            "https://ftc.test/charity/1234567.json": ExternalValidatorError("HTTP 503"),
            "https://ftc.test/company/1234567.json": ExternalValidatorError("HTTP 503"),
        }
    )
    register_validator(FindThatCharityValidator(fetcher=fetcher, base_url="https://ftc.test"))


# ---------------------------------------------------------------------------
# Data fixtures (same shape as tests/test_applicant.py — kept local to avoid
# cross-test-module fixture imports)
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_ehcf(app_with_external_validation):
    config = json.loads((GRANTS_DIR / "ehcf.json").read_text())
    grant = Grant(
        slug=config["slug"],
        name=config["name"],
        status=GrantStatus(config["status"]),
        config_json=config,
    )
    _db.session.add(grant)
    _db.session.flush()

    schema = json.loads((FORMS_DIR / "ehcf-application-v1.json").read_text())
    form = Form(
        grant=grant,
        kind=FormKind.APPLICATION,
        version=int(schema.get("version", 1)),
        schema_json=schema,
    )
    _db.session.add(form)
    _db.session.commit()
    return grant, form


@pytest.fixture
def applicant(app_with_external_validation):
    org = Organisation(name="Shelter Test", contact_email="me@test.test")
    _db.session.add(org)
    _db.session.flush()
    user = User(
        email="me@test.test",
        password_hash=generate_password_hash("correct-password-1234"),
        role=UserRole.APPLICANT,
        org_id=org.id,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


def _login(client, user, password="correct-password-1234"):
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302


def _start_app(client, applicant_user):
    _login(client, applicant_user)
    client.get("/apply/ehcf/start")
    from sqlalchemy import select

    return _db.session.execute(
        select(Application).where(Application.org_id == applicant_user.org_id)
    ).scalar_one()


# ---------------------------------------------------------------------------
# Happy path: valid registration number passes external validation
# ---------------------------------------------------------------------------


def test_save_page_passes_when_charity_number_matches(
    client, applicant, seeded_ehcf, stub_charity_hit
):
    app = _start_app(client, applicant)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "1234567",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/tasks" in response.headers["Location"]


def test_save_page_rejects_unknown_registration_number(
    client, applicant, seeded_ehcf, stub_charity_miss
):
    app = _start_app(client, applicant)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "9999999",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400  # re-renders with errors
    body = response.get_data(as_text=True)
    # Apostrophes are HTML-escaped in the rendered page; match on the
    # stable half of the sentence instead.
    assert "registered organisation with that number" in body.lower()


def test_save_page_blocks_on_network_failure(
    client, applicant, seeded_ehcf, stub_charity_network_error
):
    """Transport errors must BLOCK — the API is the gate, we never let an
    unverified number through just because the register is unreachable.
    """
    app = _start_app(client, applicant)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "1234567",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    body = response.get_data(as_text=True).lower()
    assert "unavailable" in body or "try again" in body


def test_save_page_required_error_wins_over_external_check(
    client, applicant, seeded_ehcf, stub_charity_miss
):
    """If the applicant leaves the number blank, we must not call the external
    register — the required-field message is the right thing to show."""
    app = _start_app(client, applicant)

    response = client.post(
        f"/apply/{app.id}/organisation",
        data={
            "name": "Shelter Bristol",
            "org_type": "charity",
            "registration_number": "",
            "annual_income": "450000",
            "years_serving_homeless": "5",
            "operates_in_england": "yes",
        },
    )
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "required" in body.lower()


def test_feature_flag_off_bypasses_external_validators(app_with_external_validation):
    """Flipping the feature flag off short-circuits the external call.

    This is what lets the rest of the test suite (``tests/test_applicant.py``
    in particular) keep posting the placeholder ``registration_number="12345"``
    without needing to mock a live register. We exercise the blueprint helper
    directly rather than spinning up a second Flask app — sharing the
    ``_db`` singleton across two app instances is fiddly and the direct
    call tests the same code path.
    """
    from app.applicant import _run_external_validators

    with app_with_external_validation.test_request_context():
        app_with_external_validation.config["EXTERNAL_VALIDATORS_ENABLED"] = False

        schema = json.loads((FORMS_DIR / "ehcf-application-v1.json").read_text())
        org_page = schema["pages"][0]

        # Would be rejected by the stubbed-miss validator if the feature
        # flag were on; with it off, we must get an empty error dict.
        register_validator(
            FindThatCharityValidator(fetcher=_FakeFetcher({}), base_url="https://ftc.test")
        )
        errors = _run_external_validators(org_page, {"registration_number": "99"})
        assert errors == {}
