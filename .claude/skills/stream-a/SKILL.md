---
name: stream-a
description: Context loader for Stream A (Auth and Applicant UX). Read before working on auth, registration, applicant dashboard, form page wrappers, review, or submit flows.
---

# Stream A — Auth & Applicant UX

## What This Stream Owns

**Edit freely:**
- `app/auth.py` — login, register, logout, role decorators
- `app/applicant.py` — /apply routes (dashboard, start, form_page, save_page, review, submit)
- `app/templates/auth/**` — login.html, register.html
- `app/templates/applicant/**` — dashboard.html, review.html, _flash.html, _inline_summary.html
- `tests/test_auth.py`
- `tests/test_applicant.py`

**Do NOT edit:** models.py, forms_runner.py, assessor.py, scoring.py, uploads.py,
seed.py, conftest.py, base.html, or any file not listed above.

## Public API This Stream Exposes

```python
from app.auth import applicant_required, assessor_required, login_required
```

Route names other streams may `url_for`:
- `auth.login`, `auth.register`, `auth.logout`
- `applicant.dashboard`, `applicant.start`, `applicant.form_page`,
  `applicant.save_page`, `applicant.review`, `applicant.submit`

## Imports From Other Streams

```python
# Stream B (form runner) — pure helpers
from app.forms_runner import list_pages, get_page, next_page_id, validate_page, merge_page_answers

# Stream D (models) — always available
from app.models import User, Organisation, Grant, Form, Application, UserRole, ApplicationStatus
from app.extensions import db, login_manager, csrf

# Stream D (uploads) — may be stubbed
from app.uploads import list_documents
```

## Current Implementation Status

Read `app/auth.py` and `app/applicant.py` to check what's already built.
As of the last scan, both files are **fully implemented** with:
- Auth: login/register/logout with WTForms, password hashing, role gating
- Applicant: dashboard, multi-page form navigation, review page, submit action

## Pending Work (check PLAN.md for latest)

- P2.1 Multi-page form runner depth (wrapper routes done; schema rendering is Stream B)
- P2.4 Review page refinement (temporary inline summary; waiting for Stream B's shared summary.html)
- Eligibility pre-check UI (once Stream B ships evaluate_eligibility)
- Upload integration on review page (once Stream D ships uploads)

## Key Patterns

- WTForms for login/register only. Application form pages use forms_runner.py.
- Every route needs @login_required + @applicant_required (or @assessor_required).
- Use `url_for()` for all links — never hardcode paths.
- Flash messages for success/error — use the _flash.html partial.
- Status transitions: DRAFT → SUBMITTED (via submit action). Never skip states.
