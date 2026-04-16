"""Tests for the external validators package — no outbound HTTP.

Transport is faked via a simple in-memory stub so these tests run fast,
deterministically, and without a network. The real HTTP path in
``base.http_get_json`` is covered by a separate test module that monkey-
patches ``urllib.request.urlopen`` — see ``test_external_validators_http.py``
if/when we add one.
"""

from __future__ import annotations

from typing import Any

from app.external_validators import (
    CompaniesHouseValidator,
    ExternalValidatorError,
    FindThatCharityValidator,
    ValidationResult,
    get_validator,
    register_validator,
    validate_page_external,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeFetcher:
    """Callable stub that mimics :func:`app.external_validators.base.http_get_json`.

    Configure with a dict of ``{url: response}`` where a ``dict`` response
    is returned as-is, ``None`` simulates a 404, and an
    :class:`ExternalValidatorError` (or any Exception) is raised. Also
    records every call for assertions.
    """

    def __init__(self, responses: dict[str, Any]):
        self._responses = responses
        self.calls: list[tuple[str, float, dict[str, str] | None]] = []

    def __call__(
        self,
        url: str,
        timeout: float,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append((url, timeout, headers))
        if url not in self._responses:
            # Default: 404 — prevents tests from accidentally hitting the
            # network when a URL isn't explicitly stubbed.
            return None
        value = self._responses[url]
        if isinstance(value, Exception):
            raise value
        return value


# ---------------------------------------------------------------------------
# FindThatCharityValidator
# ---------------------------------------------------------------------------


class TestFindThatCharity:
    def _validator(self, responses: dict[str, Any]) -> tuple[FindThatCharityValidator, FakeFetcher]:
        fetcher = FakeFetcher(responses)
        return (
            FindThatCharityValidator(
                fetcher=fetcher,
                base_url="https://ftc.test",
            ),
            fetcher,
        )

    def test_matches_charity_by_number_with_charity_context(self):
        validator, fetcher = self._validator(
            {"https://ftc.test/charity/1234567.json": {"name": "Shelter Bristol"}}
        )
        result = validator.validate("1234567", {"org_type": "charity"})

        assert result.ok is True
        assert result.skipped is False
        assert "Shelter Bristol" in result.message
        assert result.metadata["name"] == "Shelter Bristol"
        assert result.metadata["number"] == "1234567"
        # Confirms no second request once the first endpoint matched.
        assert len(fetcher.calls) == 1

    def test_matches_company_by_number_with_cic_context(self):
        validator, _ = self._validator(
            {"https://ftc.test/company/09876543.json": {"name": "Pathways CIC"}}
        )
        result = validator.validate("09876543", {"org_type": "CIC"})
        assert result.ok is True
        assert result.metadata["number"] == "09876543"

    def test_falls_back_to_company_endpoint_when_charity_misses(self):
        # Applicant picked "charity" but the number is actually a company.
        # We try /charity first (404), then /company (hit).
        validator, fetcher = self._validator(
            {"https://ftc.test/company/12345678.json": {"name": "Some Co Ltd"}}
        )
        result = validator.validate("12345678", {"org_type": "charity"})
        assert result.ok is True
        urls = [call[0] for call in fetcher.calls]
        assert urls == [
            "https://ftc.test/charity/12345678.json",
            "https://ftc.test/company/12345678.json",
        ]

    def test_strips_orgid_prefix_before_calling_api(self):
        validator, fetcher = self._validator(
            {"https://ftc.test/charity/1234567.json": {"name": "OK"}}
        )
        result = validator.validate("GB-CHC-1234567", {"org_type": "charity"})
        assert result.ok is True
        assert fetcher.calls[0][0] == "https://ftc.test/charity/1234567.json"

    def test_tolerates_mixed_punctuation_and_whitespace(self):
        validator, _ = self._validator({"https://ftc.test/charity/1234567.json": {"name": "OK"}})
        assert validator.validate(" 1234567 ", {"org_type": "charity"}).ok
        assert validator.validate("1,234,567", {"org_type": "charity"}).ok

    def test_rejects_when_no_endpoint_matches(self):
        # Every endpoint returns 404 → definitive "not found".
        validator, fetcher = self._validator({})
        result = validator.validate("9999999", {"org_type": "charity"})
        assert result.ok is False
        assert result.skipped is False
        assert "couldn't find" in result.message.lower()
        # Tried both charity and company endpoints.
        assert len(fetcher.calls) == 2

    def test_blocks_on_transport_error(self):
        # User wants the API to be the gate — transport errors BLOCK the
        # applicant rather than silently letting them through.
        validator, _ = self._validator(
            {
                "https://ftc.test/charity/1234567.json": ExternalValidatorError("HTTP 503"),
                "https://ftc.test/company/1234567.json": ExternalValidatorError("HTTP 503"),
            }
        )
        result = validator.validate("1234567", {"org_type": "charity"})
        assert result.ok is False
        assert result.skipped is False
        assert "unavailable" in result.message.lower() or "try again" in result.message.lower()

    def test_rejects_empty_input(self):
        validator, fetcher = self._validator({})
        result = validator.validate("", {"org_type": "charity"})
        assert result.ok is False
        assert fetcher.calls == []

    def test_falls_back_when_org_type_missing(self):
        # No org_type context → try the default fallback order
        # (charity first, then company).
        validator, fetcher = self._validator(
            {"https://ftc.test/company/12345678.json": {"name": "Some Co Ltd"}}
        )
        result = validator.validate("12345678", {})
        assert result.ok is True
        urls = [call[0] for call in fetcher.calls]
        assert urls == [
            "https://ftc.test/charity/12345678.json",
            "https://ftc.test/company/12345678.json",
        ]

    def test_extracts_org_name_from_alternative_keys(self):
        validator, _ = self._validator(
            {"https://ftc.test/charity/1234567.json": {"organisation_name": "Homes First"}}
        )
        result = validator.validate("1234567", {"org_type": "charity"})
        assert result.metadata["name"] == "Homes First"

    def test_random_string_is_rejected_via_api_404(self):
        # The core promise: a random string submitted by an applicant hits
        # the API, gets a 404, and is rejected. No offline bypass.
        validator, fetcher = self._validator({})
        result = validator.validate("asdfghjkl", {"org_type": "charity"})
        assert result.ok is False
        assert len(fetcher.calls) >= 1


# ---------------------------------------------------------------------------
# CompaniesHouseValidator
# ---------------------------------------------------------------------------


class TestCompaniesHouse:
    def test_skips_when_no_api_key_configured(self):
        validator = CompaniesHouseValidator(api_key=None, fetcher=FakeFetcher({}))
        result = validator.validate("12345678", {})
        assert result.ok is True
        assert result.skipped is True
        assert result.metadata == {"reason": "no_api_key"}

    def test_matches_active_company_when_key_configured(self):
        fetcher = FakeFetcher(
            {
                "https://api.test/company/12345678": {
                    "company_name": "Pathways Out Ltd",
                    "company_status": "active",
                }
            }
        )
        validator = CompaniesHouseValidator(
            api_key="test-key",
            fetcher=fetcher,
            base_url="https://api.test",
        )
        result = validator.validate("12345678", {})
        assert result.ok is True
        assert result.metadata["status"] == "active"
        # HTTP Basic header is attached.
        assert fetcher.calls[0][2] is not None
        assert fetcher.calls[0][2]["Authorization"].startswith("Basic ")

    def test_flags_dissolved_company_as_invalid(self):
        fetcher = FakeFetcher(
            {
                "https://api.test/company/12345678": {
                    "company_name": "Old Co",
                    "company_status": "dissolved",
                }
            }
        )
        validator = CompaniesHouseValidator(
            api_key="test-key",
            fetcher=fetcher,
            base_url="https://api.test",
        )
        result = validator.validate("12345678", {})
        assert result.ok is False
        assert "dissolved" in result.message.lower()

    def test_rejects_malformed_number(self):
        validator = CompaniesHouseValidator(
            api_key="test-key",
            fetcher=FakeFetcher({}),
            base_url="https://api.test",
        )
        result = validator.validate("!", {})
        assert result.ok is False
        assert "valid" in result.message.lower()

    def test_skips_on_transport_error(self):
        fetcher = FakeFetcher({"https://api.test/company/12345678": ExternalValidatorError("boom")})
        validator = CompaniesHouseValidator(
            api_key="test-key",
            fetcher=fetcher,
            base_url="https://api.test",
        )
        result = validator.validate("12345678", {})
        assert result.ok is True
        assert result.skipped is True

    def test_not_found_is_user_facing_error(self):
        validator = CompaniesHouseValidator(
            api_key="test-key",
            fetcher=FakeFetcher({}),  # 404 default
            base_url="https://api.test",
        )
        result = validator.validate("12345678", {})
        assert result.ok is False
        assert result.skipped is False


# ---------------------------------------------------------------------------
# validate_page_external — the page-level runner
# ---------------------------------------------------------------------------


class _StubValidator:
    """Bare-minimum validator used by page-level runner tests."""

    def __init__(self, name: str, result: ValidationResult, capture: list | None = None):
        self.name = name
        self._result = result
        self.calls = capture if capture is not None else []

    def validate(self, value: str, context: dict[str, Any]) -> ValidationResult:
        self.calls.append((value, context))
        return self._result


PAGE = {
    "id": "organisation",
    "fields": [
        {"id": "org_type", "type": "radio"},
        {
            "id": "registration_number",
            "type": "text",
            "external_validator": {
                "name": "stub_ok",
                "context_fields": ["org_type"],
            },
        },
    ],
}


def test_runner_returns_empty_when_no_external_validator_configured():
    page = {"fields": [{"id": "name", "type": "text"}]}
    errors, metadata = validate_page_external(page, {"name": "Alice"})
    assert errors == {}
    assert metadata == {}


def test_runner_invokes_validator_and_passes_context():
    stub = _StubValidator("stub_ok", ValidationResult(ok=True, metadata={"name": "X Charity"}))
    errors, metadata = validate_page_external(
        PAGE,
        {"org_type": "charity", "registration_number": "1234567"},
        registry={"stub_ok": stub},
    )
    assert errors == {}
    assert metadata == {"registration_number": {"name": "X Charity"}}
    assert stub.calls == [("1234567", {"org_type": "charity"})]


def test_runner_surfaces_failures_as_errors():
    stub = _StubValidator("stub_ok", ValidationResult(ok=False, message="Nope"))
    errors, _ = validate_page_external(
        PAGE,
        {"org_type": "charity", "registration_number": "1234567"},
        registry={"stub_ok": stub},
    )
    assert errors == {"registration_number": "Nope"}


def test_runner_skips_fields_already_in_existing_errors():
    stub = _StubValidator("stub_ok", ValidationResult(ok=False, message="Nope"))
    errors, _ = validate_page_external(
        PAGE,
        {"org_type": "charity", "registration_number": "1234567"},
        existing_errors={"registration_number": "This field is required"},
        registry={"stub_ok": stub},
    )
    # Validator was never called because the field already failed required.
    assert errors == {}
    assert stub.calls == []


def test_runner_skips_blank_values():
    stub = _StubValidator("stub_ok", ValidationResult(ok=False, message="Nope"))
    errors, _ = validate_page_external(
        PAGE,
        {"org_type": "charity", "registration_number": ""},
        registry={"stub_ok": stub},
    )
    # An empty value is the required-validator's problem, not ours.
    assert errors == {}
    assert stub.calls == []


def test_runner_skipped_results_do_not_error():
    stub = _StubValidator("stub_ok", ValidationResult(ok=True, skipped=True, message="later"))
    errors, _ = validate_page_external(
        PAGE,
        {"org_type": "charity", "registration_number": "1234567"},
        registry={"stub_ok": stub},
    )
    assert errors == {}


def test_runner_silently_ignores_missing_validator():
    # A schema may reference a validator the process hasn't registered (e.g.
    # Companies House without its API key). Pretend the registry is empty.
    errors, _ = validate_page_external(
        PAGE,
        {"org_type": "charity", "registration_number": "1234567"},
        registry={},
    )
    assert errors == {}


def test_runner_forwards_inline_config_as_context():
    # Arbitrary extra keys in the external_validator block should be passed
    # through as context so grants can tune validators from JSON without
    # code changes.
    page = {
        "fields": [
            {
                "id": "reg",
                "type": "text",
                "external_validator": {
                    "name": "stub",
                    "context_fields": [],
                    "register": "charity",
                },
            }
        ]
    }
    stub = _StubValidator("stub", ValidationResult(ok=True))
    errors, _ = validate_page_external(page, {"reg": "x"}, registry={"stub": stub})
    assert errors == {}
    assert stub.calls == [("x", {"register": "charity"})]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_default_registry_includes_find_that_charity_and_companies_house():
    # These are registered at import time by ``app.external_validators``.
    assert get_validator("find_that_charity") is not None
    assert get_validator("companies_house") is not None
    assert get_validator("made-up-name") is None


def test_register_validator_is_idempotent_and_replaces():
    class _Fake:
        name = "test_fake"

        def validate(self, value, context):
            return ValidationResult(ok=True)

    a = _Fake()
    b = _Fake()
    register_validator(a)
    assert get_validator("test_fake") is a
    register_validator(b)
    assert get_validator("test_fake") is b
