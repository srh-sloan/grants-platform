"""Validator for UK charity / company registration numbers.

Backed by findthatcharity.uk — the free, keyless aggregator of the four
official UK registers (Charity Commission E&W, OSCR, CCNI, Companies House).
Source: https://findthatcharity.uk

Endpoints used:

* ``GET /charity/<number>.json`` — charity record as JSON
* ``GET /company/<number>.json`` — company record as JSON

We pick the endpoint based on the applicant's declared ``org_type`` and
fall back to the other one if the first misses. Both endpoints return a
clean HTTP 404 when the number isn't in any register.

**The API is the source of truth.** There is no offline / regex fallback.
If the API says the number isn't registered, we reject. If the API is
unreachable, we reject with a "please try again" message — we do not let
applicants through with unverified numbers.
"""

from __future__ import annotations

import logging
from typing import Any

from app.external_validators.base import (
    ExternalValidatorError,
    JsonFetcher,
    ValidationResult,
    http_get_json,
)

log = logging.getLogger(__name__)

_CHARITY_PATH = "/charity/{number}.json"
_COMPANY_PATH = "/company/{number}.json"

# Order of endpoints to try, keyed by the applicant's declared org type.
# First hit wins; if the first endpoint 404s we try the other before giving
# up (covers the case where an applicant picks the wrong org type).
_ORG_TYPE_PATHS: dict[str, tuple[str, ...]] = {
    "charity": (_CHARITY_PATH, _COMPANY_PATH),
    "CIO": (_CHARITY_PATH, _COMPANY_PATH),
    "CIC": (_COMPANY_PATH, _CHARITY_PATH),
    "CBS": (_COMPANY_PATH, _CHARITY_PATH),
    "PCC": (_CHARITY_PATH,),
}
_FALLBACK_PATHS: tuple[str, ...] = (_CHARITY_PATH, _COMPANY_PATH)


class FindThatCharityValidator:
    """Validate a UK charity or company registration number."""

    name = "find_that_charity"

    def __init__(
        self,
        *,
        fetcher: JsonFetcher = http_get_json,
        timeout: float = 5.0,
        base_url: str = "https://findthatcharity.uk",
    ) -> None:
        self._fetch = fetcher
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")

    def validate(self, value: str, context: dict[str, Any]) -> ValidationResult:
        number = self._clean(value)
        if not number:
            return ValidationResult(
                ok=False,
                message="Enter a charity or company registration number",
            )

        paths = self._paths_for(context.get("org_type"))
        transport_error: Exception | None = None
        attempted: list[str] = []

        for path in paths:
            url = f"{self._base_url}{path.format(number=number)}"
            attempted.append(url)
            try:
                body = self._fetch(url, self._timeout)
            except ExternalValidatorError as exc:
                log.warning("find_that_charity transport error for %s: %s", url, exc)
                transport_error = exc
                continue

            if body is not None:
                name = self._org_name(body)
                log.info("find_that_charity matched %s as %r", number, name)
                return ValidationResult(
                    ok=True,
                    message=f"Matched: {name}",
                    metadata={
                        "number": number,
                        "name": name,
                        "url": url,
                        "source": self._base_url,
                    },
                )

        # Every endpoint answered. Either all transport-failed, or all 404'd.
        if transport_error is not None:
            # Treat as user-facing error so we NEVER silently let an
            # unverified number through. If the API is down, the applicant
            # sees a clear message and can retry; ops sees the WARNING log.
            return ValidationResult(
                ok=False,
                message=(
                    "We couldn't verify this registration number right now — "
                    "the UK register lookup is unavailable. Please try again "
                    "in a moment."
                ),
                metadata={"number": number, "attempted": attempted},
            )

        return ValidationResult(
            ok=False,
            message=(
                "We couldn't find a UK registered organisation with that "
                "number. Check the number and that your organisation type "
                "is correct."
            ),
            metadata={"number": number, "attempted": attempted},
        )

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _clean(raw: str) -> str:
        """Normalise input for the API path.

        Accepts common shapes like ``"1234567"``, ``"SC012345"``,
        ``"1234567-1"``, ``"GB-CHC-1234567"`` and reduces them to the bare
        registration number the ``/charity/`` and ``/company/`` endpoints
        expect. Does **not** reject any shape — if the applicant typed
        something the API doesn't recognise, the API's 404 is what surfaces
        to them.
        """
        if not raw:
            return ""
        text = raw.strip().upper()
        # Drop a leading Organisation Identifier prefix if present.
        for prefix in ("GB-CHC-", "GB-SC-", "GB-NIC-", "GB-COH-"):
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        # Strip anything that isn't part of a reg number (spaces, commas),
        # but keep the subsidiary dash.
        return "".join(ch for ch in text if ch.isalnum() or ch == "-")

    @staticmethod
    def _paths_for(org_type: Any) -> tuple[str, ...]:
        if isinstance(org_type, str) and org_type:
            if org_type in _ORG_TYPE_PATHS:
                return _ORG_TYPE_PATHS[org_type]
            for key, paths in _ORG_TYPE_PATHS.items():
                if key.lower() == org_type.lower():
                    return paths
        return _FALLBACK_PATHS

    @staticmethod
    def _org_name(body: dict[str, Any]) -> str:
        for key in ("name", "organisation_name", "charity_name", "title"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for nested_key in ("organisation", "data"):
            nested = body.get(nested_key)
            if isinstance(nested, dict):
                for key in ("name", "organisation_name", "charity_name", "title"):
                    value = nested.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return "(unnamed organisation)"
