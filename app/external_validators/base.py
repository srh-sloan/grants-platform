"""Shared types for the external validators package.

This module intentionally has no runtime dependency on Flask or SQLAlchemy
so the validators can be unit-tested in isolation.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS: float = 5.0
DEFAULT_USER_AGENT: str = "grants-platform/0.1 (+https://github.com/thebobblysocks/grants-platform)"


class ExternalValidatorError(Exception):
    """Operational failure from a validator (network, 5xx, malformed response).

    Raised to signal *the lookup could not complete*, not *the user's input
    is invalid*. Callers should treat these as "skipped" — surface a gentle
    warning but don't block form submission.
    """


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a single external validator call.

    Attributes
    ----------
    ok
        ``True`` when the input passes validation (or the check was skipped
        — see ``skipped`` below). ``False`` only when the external register
        has definitively told us the value is wrong.
    message
        User-facing text. For failures, the error to render next to the
        field. For successes, optional confirmation text the caller may
        choose to display ("We matched ``<org name>``"). Always a string so
        templates don't need ``if message is not None`` guards.
    metadata
        Structured data the caller may persist or surface (matched name,
        canonical identifier, register source URL, ...). Empty dict means
        the validator had nothing extra to share.
    skipped
        ``True`` when the validator could not run to a definitive conclusion
        (network error, provider outage, missing credentials, unsupported
        context). Combined with ``ok=True`` so the runner treats it as a
        pass-through.
    """

    ok: bool
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False


JsonFetcher = Callable[..., dict[str, Any] | None]
"""Signature for the HTTP transport each validator uses.

Validators hold a reference to one of these; tests swap in fakes without
monkey-patching imports. The contract is::

    fetcher(url: str, timeout: float, *, headers: dict[str, str] | None = None)
        -> dict[str, Any] | None

A ``None`` return signals a clean HTTP 404 (the resource doesn't exist —
usually a validation failure). Any other transport problem must raise
:class:`ExternalValidatorError` so the runner can mark the field as skipped.
The ``Callable[..., ...]`` type is used so simple test fakes (``lambda url,
timeout: {...}``) don't need to declare the ``headers`` kwarg.
"""


@runtime_checkable
class ExternalValidator(Protocol):
    """Every validator implements this shape.

    ``name`` — the string key form schemas use to reference the validator.
    ``validate(value, context)`` — perform the lookup and return a
    :class:`ValidationResult`.

    ``context`` is a flat dict pre-populated by the runner from the
    ``context_fields`` declared on the schema plus any inline config keys
    from the ``external_validator`` block. Validators must treat missing /
    unknown keys defensively (log + skip, not crash).
    """

    name: str

    def validate(self, value: str, context: dict[str, Any]) -> ValidationResult: ...


# ---------------------------------------------------------------------------
# Default HTTP transport
# ---------------------------------------------------------------------------


def http_get_json(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """GET ``url`` and return parsed JSON, or ``None`` when the resource 404s.

    Raises :class:`ExternalValidatorError` on every other failure mode
    (network error, timeout, 5xx, malformed JSON).  The wording is deliberate:
    callers distinguish "the resource does not exist" (``None``, usually a
    validation failure) from "we couldn't reach the register" (exception,
    always a skip).
    """
    merged_headers = {
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if headers:
        merged_headers.update(headers)
    request = urllib.request.Request(url, headers=merged_headers)  # noqa: S310 — we only fetch HTTPS URLs we control via validator config
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ExternalValidatorError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ExternalValidatorError(f"Network error fetching {url}: {exc}") from exc

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalValidatorError(f"Invalid JSON from {url}: {exc}") from exc
