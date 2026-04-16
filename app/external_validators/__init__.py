"""External validators — pluggable lookups against third-party registers.

Use this package whenever a form field's value needs to be checked against
a live external source of truth (Charity Commission, Companies House, OSCR,
CCNI, postcode lookups, HMRC, etc.). The framework is intentionally generic
so:

* Any grant's form schema can opt in to validation by adding an
  ``external_validator`` block to any field.
* Any new data source plugs in as another class implementing the
  :class:`ExternalValidator` protocol and registering itself on the default
  registry.
* The form runner (``app.forms_runner``) stays a pure helper — this module
  owns all I/O, timeouts, retries, caching, and user-facing error wording.

Cross-stream contract
---------------------

Schema snippet (text fields only, today — extending to other types is an
additive change)::

    {
      "id": "registration_number",
      "type": "text",
      "label": "Charity or company registration number",
      "required": true,
      "external_validator": {
        "name": "find_that_charity",
        "context_fields": ["org_type"]
      }
    }

``name`` is the registry key (see :func:`get_validator`). ``context_fields``
is an optional list of other field IDs on the same page whose values are
passed to the validator as context (e.g. the applicant's declared org type
steers which UK register to query). Unknown or missing context is safe;
validators fall back to generic lookups.

Call order (blueprints): after ``forms_runner.validate_page`` returns and
basic required/word-limit validation passes, the blueprint calls
:func:`validate_page_external` to layer external checks on top. External
validators are never invoked for fields that failed basic validation or
whose value is blank — there's nothing to look up.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.external_validators.base import (
    DEFAULT_TIMEOUT_SECONDS,
    ExternalValidator,
    ExternalValidatorError,
    ValidationResult,
    http_get_json,
)
from app.external_validators.companies_house import CompaniesHouseValidator
from app.external_validators.find_that_charity import FindThatCharityValidator

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "CompaniesHouseValidator",
    "ExternalValidator",
    "ExternalValidatorError",
    "FindThatCharityValidator",
    "ValidationResult",
    "get_validator",
    "http_get_json",
    "register_validator",
    "validate_page_external",
]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ExternalValidator] = {}


def register_validator(validator: ExternalValidator) -> None:
    """Add (or replace) a validator in the default registry.

    Tests use this to inject stubs; production code uses :func:`get_validator`.
    Idempotent — re-registering the same name is how config-reloaded validators
    swap in fresh credentials.
    """
    _REGISTRY[validator.name] = validator


def get_validator(name: str) -> ExternalValidator | None:
    """Return the registered validator for ``name``, or ``None`` if missing.

    Returning ``None`` is load-bearing: if a grant's schema references a
    validator the app hasn't registered (e.g. the Companies House key isn't
    configured), we skip the external check rather than raise at form-save
    time. The applicant shouldn't be blocked because ops forgot a secret.
    """
    return _REGISTRY.get(name)


# Register the two validators that ship with the platform by default. Both
# can be overridden at runtime by re-registering under the same name.
register_validator(FindThatCharityValidator())
register_validator(CompaniesHouseValidator())


# ---------------------------------------------------------------------------
# Page-level runner
# ---------------------------------------------------------------------------


def validate_page_external(
    page: dict,
    submitted: dict,
    *,
    existing_errors: Mapping[str, str] | None = None,
    registry: Mapping[str, ExternalValidator] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Run external validators for every field on ``page`` that declares one.

    Returns a ``(errors, metadata)`` tuple.

    - ``errors`` — ``{field_id: message}`` for fields whose external lookup
      came back as "definitely invalid". Fields whose lookup failed for
      operational reasons (network, timeout, 5xx, missing validator) are
      **not** in ``errors``; we never block an applicant on an outage.
    - ``metadata`` — ``{field_id: {...}}`` of any structured data the
      validator returned on success (e.g. the matched organisation's name
      and source). Callers can persist this alongside the answer, flash it
      to the user, or feed it to the AI pre-fill layer.

    Skips fields that:

    - have no ``external_validator`` block,
    - already appear in ``existing_errors`` (they failed required /
      word-limit checks — no point asking the external register),
    - have an empty submitted value (required validation, not external).
    """
    errors: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}
    skipped_existing = dict(existing_errors or {})
    lookup = registry if registry is not None else _REGISTRY

    for field in page.get("fields") or []:
        field_id: str = field["id"]
        config = field.get("external_validator")
        if not config:
            continue
        if field_id in skipped_existing:
            continue

        value = submitted.get(field_id)
        if not _is_non_empty(value):
            continue

        validator = lookup.get(config["name"])
        if validator is None:
            # Unknown / un-configured validator — don't block the user.
            # Flagged in logs inside the validator implementations themselves.
            continue

        context = _collect_context(config, submitted)
        try:
            result = validator.validate(str(value), context)
        except ExternalValidatorError:
            # Validator decided the failure isn't user-correctable. Same
            # lenient policy as "skipped" — don't block on external errors.
            continue

        if result.skipped:
            continue
        if not result.ok:
            errors[field_id] = result.message
            continue
        if result.metadata:
            metadata[field_id] = dict(result.metadata)

    return errors, metadata


def _collect_context(config: dict, submitted: dict) -> dict[str, Any]:
    """Gather the submitted values for the validator's declared context fields."""
    fields = config.get("context_fields") or []
    context = {name: submitted.get(name) for name in fields}
    # Validators also accept arbitrary extra config keys (e.g. a "register"
    # override); forward them so grants can tweak behaviour without touching
    # Python. Reserved keys ("name", "context_fields") are stripped.
    for key, value in config.items():
        if key in {"name", "context_fields"}:
            continue
        context.setdefault(key, value)
    return context


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True
