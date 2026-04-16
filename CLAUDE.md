# Grants Platform — AI Context

Longer-form notes for Claude / any AI pair working on this repo. The `README.md`
is the source of truth for what the team has actually agreed; this file is
reference material and working context.

## Project Overview

A flexible grants application and assessment system. First grant onboarded:
the **Ending Homelessness in Communities Fund (EHCF)**, administered by MHCLG.
Two user types:

- **Applicants** — voluntary, community, and faith sector (VCFS) organisations
  applying for grant funding.
- **Assessors** — department staff reviewing, scoring, and making funding
  decisions.

The system should handle additional grants in future (see
`refs/pride-in-place-prospectus.md` as a second shape to stress-test against),
so **grant-specific things — eligibility rules, form fields, scoring criteria,
weights — live in data (JSON), not code.**

## Current direction (v0)

See `README.md`. Short version: Flask + SQLite, JSON-defined forms, session
auth, iterative thin slices. We are four people on a hackathon, so we optimise
for shipping working slices over completeness.

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | |
| Web framework | Flask | Jinja2 for templates |
| Database | SQLite | Single file, zero-config. Postgres later if we outgrow it. |
| ORM | SQLAlchemy | Optional — we may start with raw `sqlite3` if it's faster |
| Migrations | Alembic / Flask-Migrate | Defer until the schema settles |
| Auth | Flask-Login + `werkzeug.security` (or bcrypt) | Session-based |
| Forms | **JSON schemas + Flask-WTF for CSRF/validation** | Form *definitions* are JSON files; the app is a generic runner over them |
| Styling | GOV.UK Frontend | `govuk-frontend-jinja` macros + `govuk-frontend-wtf` widgets |
| File uploads | Local filesystem for v0 | S3 only if we need it |
| Deployment | Local → Render / Railway later | |

Nothing here is locked in — if someone spots a simpler option mid-hackathon,
flag it.

## Architecture (planned)

```
/ideas              ← team ideas dumped here before coding
/refs               ← prospectuses and policy docs
/app                ← Flask app (not created yet)
  __init__.py       — app factory
  models.py         — SQLAlchemy models (or db.py if we skip the ORM)
  auth.py           — login / register / logout
  applicant.py      — applicant routes
  assessor.py       — assessor routes (role-gated)
  forms_runner.py   — renders + validates forms from JSON schema
  scoring.py        — computes weighted scores from grant config
  /forms            — JSON form definitions (one per grant / per stage)
  /templates
  /static
/tests
config.py
run.py
```

---

## Data Model (flexible core)

The model is deliberately grant-agnostic. Grant-specific things hang off JSON
blobs keyed by a form schema.

### `users`
- `id`, `email`, `password_hash`, `role` (`applicant` | `assessor` | `admin`)
- `org_id` (nullable — only set for applicants)

### `organisations`
- `id`, `name`, `contact_name`, `contact_email`
- `profile_json` — org type, charity number, income, address, etc. Shape comes
  from a profile form schema, not hardcoded columns.

### `grants`
- `id`, `slug` (e.g. `ehcf`), `name`, `status` (`open` | `closed`)
- `config_json` — eligibility rules, scoring criteria and weights, award
  ranges, deadlines. Everything grant-specific lives here.

### `forms`
- `id`, `grant_id`, `kind` (`application` | `assessment` | `eligibility`)
- `version`, `schema_json` — the JSON form definition

### `applications`
- `id`, `org_id`, `grant_id`, `form_version`
- `status` (`draft` | `submitted` | `under_review` | `approved` | `rejected`)
- `answers_json` — applicant's answers, keyed to the form schema
- `submitted_at`

### `documents`
- `id`, `application_id`, `kind` (e.g. `budget`, `la_letter`), `storage_path`,
  `filename`, `uploaded_at`

### `assessments`
- `id`, `application_id`, `assessor_id`
- `scores_json` — `{criterion_id: 0..3}`, criterion IDs come from the grant config
- `notes_json` — per-criterion justifications
- `weighted_total`, `recommendation` (`fund` | `reject` | `refer`)
- `completed_at`

Columns may evolve — treat this as a starting point, not a spec.

---

## Scoring (data-driven)

Criteria, weights, and auto-reject rules come from the grant's `config_json`,
not from hardcoded constants. Rough shape:

```python
# scoring.py
def calculate_weighted_score(scores: dict, criteria: list[dict]) -> int:
    return sum(scores[c["id"]] * c["weight"] for c in criteria)

def has_auto_reject(scores: dict, criteria: list[dict]) -> bool:
    return any(
        scores[c["id"]] == 0
        for c in criteria
        if c.get("auto_reject_on_zero")
    )
```

A grant config snippet looks like:

```json
{
  "criteria": [
    {"id": "skills",    "label": "Skills and experience", "weight": 10, "max": 3, "auto_reject_on_zero": true},
    {"id": "proposal2", "label": "Proposal (Part 2)",     "weight": 30, "max": 3, "auto_reject_on_zero": true}
  ]
}
```

---

## Key User Flows

### Applicant
1. **Eligibility check** — rules from the grant config (see EHCF below).
2. **Register / sign in** — Flask-Login, password hashing.
3. **Multi-step application** — form runner renders pages from the JSON
   schema. Each page saves as draft.
4. **Upload supporting documents** — budget, project plan, LA support letter, risk register.
5. **Review & submit** — read-only summary, then submit (no withdrawal).
6. **Track status** — dashboard shows state transitions.

### Assessor
1. **Application list** — filters (status, LA area, funding type, score).
2. **Application detail** — applicant answers alongside the scoring form.
3. **Score each criterion** — 0–3 with mandatory notes.
4. **Flag for moderation** — borderline or conflicted.
5. **Allocation dashboard** — ranked by weighted score, running total against
   the grant's budget.

---

## First grant: EHCF specifics

These should end up in the EHCF grant's `config_json`, not hardcoded.

**Eligibility**
- `org_type` ∈ {charity, CIO, CIC, community benefit society, PCC}
- `annual_income` ≤ £5,000,000
- `years_serving_homeless` ≥ 3
- `operates_in_england` = true
- LA endorsement letter required before submission
- Capital funding needs a year-1 readiness checklist (planning permission,
  tenure, contractor)

**Scoring weights** (out of 300)

| Criterion | Weight | Max raw | Weighted max |
|---|---|---|---|
| Skills and experience | 10% | 3 | 30 |
| Proposal Part 1 | 10% | 3 | 30 |
| Proposal Part 2 | 30% | 3 | 90 |
| Deliverability Part 1 | 25% | 3 | 75 |
| Deliverability Part 2 | 5% | 3 | 15 |
| Cost and value | 10% | 3 | 30 |
| Outcomes and impact | 10% | 3 | 30 |

Any criterion scoring 0 → auto-reject.

**Fund context**
- Total: £37m over 3 years (2026–2029)
- Per-award: £50k–£200k/year revenue; £50k–£200k capital (year 1 or 2 only)
- Contact: ehcf@communities.gov.uk
- Prospectus: https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus

---

## GOV.UK Frontend Setup

### Flask app factory (`app/__init__.py`)
```python
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader
from govuk_frontend_wtf.main import WTFormsHelpers

def create_app():
    app = Flask(__name__)

    app.jinja_loader = ChoiceLoader([
        PackageLoader("app"),
        PrefixLoader({
            "govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja"),
            "govuk_frontend_wtf": PackageLoader("govuk_frontend_wtf"),
        }),
    ])

    WTFormsHelpers(app)
    # ... register blueprints, db, login_manager etc.
```

### Base template (`templates/base.html`)
```html
<!DOCTYPE html>
<html lang="en" class="govuk-template">
<head>
  <link rel="stylesheet" href="{{ url_for('static', filename='govuk-frontend.min.css') }}">
</head>
<body class="govuk-template__body">
  {% from 'govuk_frontend_jinja/components/skip-link/macro.html' import govukSkipLink %}
  {{ govukSkipLink({'text': 'Skip to main content', 'href': '#main-content'}) }}
  {% include 'partials/header.html' %}
  <div class="govuk-width-container">
    <main class="govuk-main-wrapper" id="main-content">
      {% block content %}{% endblock %}
    </main>
  </div>
  <script src="{{ url_for('static', filename='govuk-frontend.min.js') }}"></script>
</body>
</html>
```

### Static assets
Download `govuk-frontend.min.css` and `govuk-frontend.min.js` from the
[GOV.UK Frontend releases](https://github.com/alphagov/govuk-frontend/releases)
and place in `app/static/`.

---

## WTForms Usage Boundaries

WTForms is used **only** for forms with static, known-at-build-time fields:
- Login / registration
- Assessor scoring (always the same shape: score + notes per criterion)

**Do not use WTForms for application form sections.** Those fields are defined
in the JSON schema and rendered by `forms_runner.py` via GOV.UK Jinja macros
directly. This keeps the door open for a no-code form builder later without
requiring structural changes.

---

## Seed Data (for hackathon)

Populate `grants` and `forms` via a `seed.py` script using EHCF as the first
grant. This proves out the data-driven approach without needing an admin UI on
day one. See `refs/ehcf-prospectus.md` for the source data.

---

## Environment

```
FLASK_SECRET_KEY=
DATABASE_URL=sqlite:///grants.db      # or the Flask config equivalent
UPLOAD_FOLDER=uploads/
```
