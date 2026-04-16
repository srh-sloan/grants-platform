"""Validator backed by the UK Companies House Public Data API.

The API is free but **requires** an API key (register at
https://developer.company-information.service.gov.uk/). Until the key is
configured in the environment this validator reports itself as "skipped"
rather than raising — grants that reference it keep working, they just
don't get the secondary check.

We ship this as a second validator specifically to prove out the pluggable
pattern: the same JSON form schema can point at either
``find_that_charity`` (no key, aggregator) or ``companies_house`` (gold-
standard primary source) and the runner picks up whichever is registered
with credentials. Grants that need both can register under different
``name`` keys and run both in sequence.

Environment
-----------

Set ``COMPANIES_HOUSE_API_KEY`` in the Flask config or the process env;
:func:`app.__init__.create_app` is responsible for reading it and
re-registering this validator with the live key. During tests the key is
unset, so the validator degrades to ``skipped`` and existing assertions
keep passing.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any

from app.external_validators.base import (
    DEFAULT_TIMEOUT_SECONDS,
    ExternalValidatorError,
    JsonFetcher,
    ValidationResult,
    http_get_json,
)

log = logging.getLogger(__name__)

# SSRF protection: only ever contact the canonical Companies House API host.
_ALLOWED_BASE_URL = "https://api.company-information.service.gov.uk"

# Companies House numbers are 8 chars: either 8 digits, or 2 letters + 6 digits
# (SC######, NI######, OC######, etc.). We accept either shape but normalise
# to uppercase alphanumerics only before dispatch.
_NON_IDENTIFIER = re.compile(r"[^A-Z0-9]")
_VALID_SHAPE = re.compile(r"^[A-Z0-9]{6,10}$")


class CompaniesHouseValidator:
    """Validate a UK company number against Companies House.

    Parameters
    ----------
    api_key
        Companies House public data API key. When ``None`` (the default),
        the validator skips every call — existing applicants are not blocked
        by missing credentials.
    fetcher
        JSON GET function — tests inject a fake.
    timeout
        Per-request timeout in seconds.
    base_url
        Override for the API root (defaults to the public endpoint).
    """

    name = "companies_house"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: JsonFetcher = http_get_json,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        base_url: str = _ALLOWED_BASE_URL,
    ) -> None:
        # Allow env-based fallback so blueprints can ``register_validator(
        # CompaniesHouseValidator())`` once and pick up credentials from the
        # process environment without threading config everywhere.
        self._api_key = api_key or os.environ.get("COMPANIES_HOUSE_API_KEY") or None
        self._fetch = fetcher
        self._timeout = timeout
        # SSRF guard: when using the real HTTP fetcher, only the canonical host
        # is permitted. Tests inject a fake fetcher so the URL never hits the
        # network — they can supply any base_url for URL-construction assertions.
        if fetcher is http_get_json and base_url.rstrip("/") != _ALLOWED_BASE_URL:
            raise ValueError(
                f"base_url must be '{_ALLOWED_BASE_URL}' when using the default HTTP fetcher."
            )
        self._base_url = base_url.rstrip("/")

    def validate(self, value: str, context: dict[str, Any]) -> ValidationResult:
        if not self._api_key:
            # No credentials → silent skip. Logged at INFO (not WARNING) so
            # unconfigured dev environments don't spam the log.
            log.info("companies_house validator skipped: no API key configured")
            return ValidationResult(
                ok=True,
                skipped=True,
                message="",
                metadata={"reason": "no_api_key"},
            )

        normalised = _NON_IDENTIFIER.sub("", (value or "").upper())
        if not _VALID_SHAPE.match(normalised):
            return ValidationResult(
                ok=False,
                message="Enter a valid UK company number (6 to 10 letters or digits)",
            )

        url = f"{self._base_url}/company/{normalised}"
        # Companies House uses HTTP Basic with the API key as the "username"
        # and an empty password. The shared ``http_get_json`` accepts arbitrary
        # headers so we bolt Authorization on here rather than maintaining a
        # separate transport.
        headers = {"Authorization": self._basic_auth_header(self._api_key)}

        try:
            body = self._fetch(url, self._timeout, headers=headers)
        except ExternalValidatorError as exc:
            return self._skip_on_error(normalised, exc)

        if body is None:
            return ValidationResult(
                ok=False,
                message=(
                    "We couldn't find a UK company with that number. "
                    "Check the number on your Certificate of Incorporation."
                ),
                metadata={"number": normalised},
            )

        name = body.get("company_name") or "(unnamed company)"
        status = body.get("company_status")
        if isinstance(status, str) and status.lower() in {"dissolved", "liquidation"}:
            return ValidationResult(
                ok=False,
                message=(
                    f"Company {normalised} is recorded as {status} at Companies House. "
                    "Only active companies can apply."
                ),
                metadata={"number": normalised, "name": name, "status": status},
            )

        return ValidationResult(
            ok=True,
            message=f"Matched: {name}",
            metadata={
                "number": normalised,
                "name": name,
                "status": status,
                "source": self._base_url,
            },
        )

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _basic_auth_header(api_key: str) -> str:
        # Companies House expects the API key as the "username" in HTTP Basic
        # auth with no password. We build the header manually to keep the
        # shared HTTP helper generic.
        token = base64.b64encode(f"{api_key}:".encode("ascii")).decode("ascii")
        return f"Basic {token}"

    @staticmethod
    def _skip_on_error(number: str, exc: Exception) -> ValidationResult:
        log.warning("companies_house lookup failed for %s: %s", number, exc)
        return ValidationResult(
            ok=True,
            skipped=True,
            message=(
                "We couldn't verify this company number right now. "
                "You can continue; we'll check it again when you submit."
            ),
            metadata={"number": number},
        )
