"""JSON-driven form runner — pure helpers for schema traversal + validation.

**Stream ownership:** Form runner (Stream B).

The applicant blueprint (Stream A) calls into these helpers; it never walks
the form schema itself. Keep this module free of Flask, DB, and I/O so it can
be unit-tested in isolation.

Schema contract (pinned in Phase 0 — see ``CONTRIBUTING.md``)::

    {
      "id": "ehcf-application",
      "version": 1,
      "kind": "application",
      "pages": [
        {
          "id": "organisation",
          "title": "About your organisation",
          "fields": [
            {"id": "name", "type": "text", "label": "...", "required": true},
            ...
          ]
        }
      ]
    }

Supported field ``type`` values (adding a new type requires a new runner handler
AND a new Jinja macro — coordinate across streams before doing so):

``text``, ``textarea``, ``radio``, ``checkbox``, ``select``, ``number``,
``currency``, ``date``, ``file``.

Field type extensions:

``textarea`` fields may include::

    "word_limit": 500    — optional int, validation error if answer exceeds N words

Word count is ``len(value.split())``: whitespace-separated tokens.  The check
only runs when the field has a non-empty value; a blank value on a required
textarea reports a required error, not a word-count error.

Conditional visibility (P4.3):

Any field may include an optional ``visible_when`` object that controls whether
the field is shown and validated::

    "visible_when": {"field": "funding_type", "operator": "in", "value": ["capital", "both"]}

Supported operators: ``in``, ``equals``, ``not_equals``.  When a field is
hidden (condition evaluates false), it is skipped during validation so a
hidden required field does not produce an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field

SUPPORTED_FIELD_TYPES: frozenset[str] = frozenset(
    {"text", "textarea", "radio", "checkbox", "select", "number", "currency", "date", "file"}
)


# ---------------------------------------------------------------------------
# Schema traversal
# ---------------------------------------------------------------------------


def list_pages(schema: dict) -> list[dict]:
    """Return the pages list in order; empty list if the schema has none."""
    return list(schema.get("pages") or [])


def get_page(schema: dict, page_id: str) -> dict | None:
    """Find a page by its ID, or None if missing."""
    for page in list_pages(schema):
        if page.get("id") == page_id:
            return page
    return None


def next_page_id(schema: dict, current_page_id: str) -> str | None:
    """ID of the page after ``current_page_id``, or None if at the end."""
    pages = list_pages(schema)
    for idx, page in enumerate(pages):
        if page.get("id") == current_page_id and idx + 1 < len(pages):
            return pages[idx + 1]["id"]
    return None


def prev_page_id(schema: dict, current_page_id: str) -> str | None:
    """ID of the page before ``current_page_id``, or None if at the start."""
    pages = list_pages(schema)
    for idx, page in enumerate(pages):
        if page.get("id") == current_page_id and idx > 0:
            return pages[idx - 1]["id"]
    return None


def get_page_position(schema: dict, page_id: str) -> tuple[int, int]:
    """Return ``(1-based position, total pages)`` for the given ``page_id``.

    Raises :exc:`ValueError` if ``page_id`` is not found in the schema.

    Stream A calls this and passes ``page_number`` and ``total_pages`` to the
    ``forms/page.html`` template to render the "Page X of Y" indicator.
    """
    pages = list_pages(schema)
    for idx, page in enumerate(pages):
        if page.get("id") == page_id:
            return (idx + 1, len(pages))
    raise ValueError(f"page_id {page_id!r} not found in schema")


# ---------------------------------------------------------------------------
# Conditional visibility (P4.3)
# ---------------------------------------------------------------------------


def is_field_visible(field: dict, answers: dict) -> bool:
    """Evaluate whether *field* should be shown given current *answers*.

    Returns ``True`` when the field has no ``visible_when`` condition or when
    the condition is met.  *answers* is a flat ``{field_id: value}`` dict for
    the current page.

    Supported operators:

    - ``"in"``         — answer value is contained in the given list.
    - ``"equals"``     — answer value equals the given scalar.
    - ``"not_equals"`` — answer value does not equal the given scalar.
    """
    condition = field.get("visible_when")
    if not condition:
        return True

    trigger_value = answers.get(condition["field"])
    operator = condition["operator"]

    if operator == "in":
        return trigger_value in condition["value"]
    if operator == "equals":
        return trigger_value == condition["value"]
    if operator == "not_equals":
        return trigger_value != condition["value"]

    raise ValueError(f"Unknown visible_when operator: {operator!r}")


def visible_fields(page: dict, answers: dict) -> list[dict]:
    """Return only the fields from *page* that should be displayed."""
    return [f for f in (page.get("fields") or []) if is_field_visible(f, answers)]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_page(page: dict, submitted: dict) -> dict[str, str]:
    """Validate a single page's submission against its schema.

    Returns a mapping of ``field_id -> error message`` for invalid fields.
    An empty dict means the submission is valid.

    Checks performed (in order per field):

    1. **Required** — if ``required`` is true and the value is blank/absent.
    2. **Word limit** — if ``type`` is ``textarea`` and ``word_limit`` is set,
       the answer must not exceed that many whitespace-separated tokens.
       Word-limit is only checked when the field has a non-empty value so it
       never double-reports alongside the required error.
    """
    errors: dict[str, str] = {}
    for field in page.get("fields") or []:
        if field.get("type") not in SUPPORTED_FIELD_TYPES:
            raise ValueError(
                f"Field {field.get('id')!r} has unsupported type {field.get('type')!r}"
            )

        # Skip validation for fields hidden by a visible_when condition.
        if not is_field_visible(field, submitted):
            continue

        field_id: str = field["id"]
        value = submitted.get(field_id)

        # 1. Required check — runs first; if it fires we skip word-limit.
        if field.get("required") and not _has_value(value):
            errors[field_id] = "This field is required"
            continue

        # 2. Word-limit check — textarea only, only when a non-empty value exists.
        if (
            field.get("type") == "textarea"
            and "word_limit" in field
            and _has_value(value)
        ):
            word_limit: int = field["word_limit"]
            actual_count = len(str(value).split())
            if actual_count > word_limit:
                errors[field_id] = (
                    f"Answer must be {word_limit} words or fewer"
                    f" (your answer is {actual_count} words)"
                )

    return errors


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# ---------------------------------------------------------------------------
# Answer merging (draft save)
# ---------------------------------------------------------------------------


def merge_page_answers(
    existing_answers: dict,
    page_id: str,
    page_submission: dict,
) -> dict:
    """Merge a page's submitted fields into the existing ``answers_json`` blob.

    Answers are stored as ``{page_id: {field_id: value}}``. Callers pass the
    full existing blob and the new page data; this returns a new dict
    (existing input is not mutated).
    """
    merged = dict(existing_answers)
    merged[page_id] = {**(merged.get(page_id) or {}), **page_submission}
    return merged


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def format_answer(field: dict, value: object) -> str:
    """Format a field value for human-readable display in summaries.

    Returns an empty string for ``None`` or ``""`` so callers can apply their
    own "Not answered" fallback.  For all other types:

    - ``currency`` — ``"£50,000"`` (comma-separated thousands, £ prefix)
    - ``number`` — whole numbers drop the trailing ``.0``; decimals kept as-is
    - ``radio`` / ``select`` — returns the matching ``option["label"]``, falls
      back to the raw value string if no option matches
    - ``checkbox`` — ``"Yes"`` when truthy (handles ``True``, ``"true"``,
      ``"yes"``); ``"No"`` otherwise
    - ``date``, ``textarea``, ``text``, ``file`` — ``str(value)``
    """
    if value is None or value == "":
        return ""

    field_type = field.get("type", "text")

    if field_type == "currency":
        try:
            return f"£{int(float(str(value))):,}"
        except ValueError:
            return str(value)

    if field_type == "number":
        try:
            float_val = float(str(value))
            return str(int(float_val)) if float_val == int(float_val) else str(float_val)
        except ValueError:
            return str(value)

    if field_type in ("radio", "select"):
        for option in field.get("options") or []:
            if option.get("value") == value:
                return option["label"]
        return str(value)

    if field_type == "checkbox":
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, str):
            return "Yes" if value.lower() in ("true", "yes", "1") or value.strip() else "No"
        return "Yes" if value else "No"

    return str(value)


# ---------------------------------------------------------------------------
# Eligibility evaluator — reads rules from ``grant.config_json["eligibility"]``
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EligibilityResult:
    """Outcome of evaluating a set of eligibility rules against answers.

    - ``passed`` — all rules evaluated true.
    - ``failures`` — list of rule ``id``s that failed (ordered as declared).
    - ``labels`` — ``{rule_id: human-readable label}`` for rendering.
    """

    passed: bool
    failures: list[str] = dataclass_field(default_factory=list)
    labels: dict[str, str] = dataclass_field(default_factory=dict)


def evaluate_eligibility(rules: list[dict], answers: dict) -> EligibilityResult:
    """Evaluate ``rules`` against a flat ``{field_id: value}`` dict.

    Rule shape (owned by Stream D, see ``seed/grants/ehcf.json``)::

        {"id": "annual_income", "type": "max", "label": "...", "value": 5000000}
        {"id": "org_type", "type": "in", "values": [...]}
        {"id": "operates_in_england", "type": "equals", "value": true}
        {"id": "years_serving_homeless", "type": "min", "value": 3}
    """
    failures: list[str] = []
    labels: dict[str, str] = {rule["id"]: rule["label"] for rule in rules}

    for rule in rules:
        if not _check_rule(rule, answers):
            failures.append(rule["id"])

    return EligibilityResult(passed=len(failures) == 0, failures=failures, labels=labels)


def _normalise_bool(value: object) -> bool | None:
    """Normalise boolean-ish values to Python bool, or return None if not boolean-ish."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "yes"):
            return True
        if value.lower() in ("false", "no"):
            return False
    return None


def _check_rule(rule: dict, answers: dict) -> bool:
    """Return True if the rule passes for the given answers, False if it fails.

    Raises ValueError for unknown rule types.
    """
    rule_id: str = rule["id"]
    rule_type: str = rule["type"]

    if rule_id not in answers:
        return False

    raw = answers[rule_id]

    if rule_type == "in":
        return str(raw) in rule["values"]

    if rule_type == "equals":
        expected = rule["value"]
        # If expected is a Python bool, normalise the answer before comparing.
        if isinstance(expected, bool):
            normalised = _normalise_bool(raw)
            if normalised is None:
                return False
            return normalised == expected
        return raw == expected

    if rule_type == "max":
        try:
            return float(raw) <= rule["value"]
        except (TypeError, ValueError):
            return False

    if rule_type == "min":
        try:
            return float(raw) >= rule["value"]
        except (TypeError, ValueError):
            return False

    raise ValueError(f"Unknown rule type: {rule_type!r}")
