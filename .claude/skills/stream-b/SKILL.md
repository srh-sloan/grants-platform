---
name: stream-b
description: Context loader for Stream B (Form Runner). Read before working on JSON schema rendering, field validation, eligibility evaluation, or form templates.
---

# Stream B — Form Runner

## What This Stream Owns

**Edit freely:**
- `app/forms_runner.py` — pure helpers (no Flask, no DB, no I/O)
- `app/forms/*.json` — JSON form definitions (EHCF schemas)
- `app/templates/forms/**` — page.html, summary.html, field macros
- `tests/test_forms_runner.py`
- `tests/test_forms_templates.py` (create if needed)

**Do NOT edit:** auth.py, applicant.py, assessor.py, scoring.py, models.py,
uploads.py, seed.py, or any file not listed above.

## Public API This Stream Exposes

```python
from app.forms_runner import (
    list_pages, get_page, next_page_id, prev_page_id,
    validate_page, merge_page_answers,
    evaluate_eligibility, EligibilityResult,
    SUPPORTED_FIELD_TYPES,
)
```

Shared templates (rendered by other streams):
- `templates/forms/page.html` — context: `{form, application, page, answers, errors, back_url, action_url}`
- `templates/forms/summary.html` — context: `{schema, answers, documents}`

## Imports From Other Streams

**None.** This stream is pure — no Flask, no DB, no imports from other streams.
The templates use GOV.UK Frontend macros directly and consume route action URLs
built by Stream A.

## Current Implementation Status

Read `app/forms_runner.py` to check. As of last scan:
- `list_pages`, `get_page`, `next_page_id`, `prev_page_id` — **implemented**
- `validate_page` — **implemented** (required-field check)
- `merge_page_answers` — **implemented**
- `evaluate_eligibility` — **STUB** (raises NotImplementedError)
- `EligibilityResult` — **implemented** (dataclass)

## Pending Work (check PLAN.md for latest)

- P2.2 Eligibility pre-check: implement `evaluate_eligibility(rules, answers)` pure helper
  - Rules come from `grant.config_json.eligibility` (see seed/grants/ehcf.json)
  - Rule shapes: `{type: "max_value", field: "annual_income", value: 5000000}`,
    `{type: "in_set", field: "org_type", values: ["charity", "CIO", ...]}`,
    `{type: "min_value", field: "years_serving_homeless", value: 3}`,
    `{type: "equals", field: "operates_in_england", value: true}`
  - Return EligibilityResult with pass/fail and reasons
- P2.1 Multi-page depth: error-summary component, "Back" navigation, page progress
- P4.2 Word-limit validator (future — second grant)
- P4.3 Conditional field visibility (future — EHCF capital/readiness)

## Key Patterns

- **Pure functions only.** No Flask app context, no DB, no file I/O.
  Take data in (schema dict, answers dict, rules list), return data out.
- **Field types are frozen:** text, textarea, radio, checkbox, select, number,
  currency, date, file. Adding one needs a runner handler AND a Jinja macro.
- **Form schema contract:** `{id, version, pages: [{id, title, fields: [{id, type, label, required, ...}]}]}`
- **Answers payload:** `{page_id: {field_id: value}}`
- **Templates use GOV.UK macros** — govukInput, govukRadios, govukTextarea, etc.
  Don't write raw `<input>` tags.
- **Error summary** at the top of form pages on validation failure.
