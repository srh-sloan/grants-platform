# Grants Platform — AI Context

Longer-form notes for Claude / any AI pair working on this repo. The `README.md`
is the source of truth for what the team has actually agreed; this file is
reference material and working context. `PLAN.md` holds the feature
catalogue, phase ordering, and parallel-stream breakdown — consult it before
picking up work so you don't duplicate another stream or jump phases.

## Read this first (operating mode)

This is a **one-day, four-person hackathon** building an **iterative, modular,
innovative MVP**. Your job as AI pair is to produce code and docs that look
like they were written by one team, not five individuals on different days.
That means following the patterns in this file even when a different approach
would be locally simpler.

Before acting on any task:

1. **Locate the task in `PLAN.md`.** Which phase? Which stream? If you can't
   place it, ask — don't guess. Don't start phase N+1 work while phase N is
   unfinished.
2. **Pick the thinnest slice that demos.** If the prompt implies a full
   feature, propose a thin slice first and confirm. "One page, one field, one
   grant, happy path" beats half-built breadth.
3. **Prefer config over code.** If the change would hardcode grant-specific
   behaviour (EHCF weights, EHCF eligibility, EHCF field labels) into Python
   or templates, stop. It belongs in `grants.config_json` or
   `forms.schema_json`.
4. **Respect stream boundaries.** Each stream owns a set of files (see
   `PLAN.md` → Parallelisation summary). If a task needs a file outside your
   stream, prefer adding to a contract (e.g. a model column, a helper
   function) over reaching across and restructuring someone else's code.
5. **Leave `main` runnable.** Every commit should boot the app and pass
   `pytest`. If a change can't land atomically, land a stub first.

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

---

## Working patterns for Claude (binding conventions)

These are the **generic patterns every AI contribution must follow** so that
code produced across the four parallel streams looks like one codebase.
Deviations should be flagged up and agreed with the team, not slipped in.

### 1. MVP mindset

- **Smallest runnable slice wins.** If in doubt, hardcode a value, stub a
  branch, or fake a return — get the slice green, then iterate.
- **No speculative generality.** Don't add config knobs, plugin hooks, or
  abstract base classes "for later". The second grant in Phase 4 will teach
  us what's actually shared.
- **No polish passes on unfinished phases.** Formatting a file Claude didn't
  touch this task is out of scope; fixing unrelated bugs is out of scope.
- **When unsure, propose then build.** For anything beyond a one-file change,
  sketch the plan in one paragraph, get a nod, then code.

### 2. File & directory conventions

- **Python files:** `snake_case.py`. Blueprints live at `app/<name>.py`
  (`auth.py`, `applicant.py`, `assessor.py`, `forms_runner.py`, `scoring.py`).
- **Templates:** `app/templates/<blueprint>/<action>.html`
  (e.g. `applicant/dashboard.html`, `assessor/score.html`). Shared chrome in
  `app/templates/partials/`. Always extend `base.html`.
- **Static assets:** `app/static/` (flat). GOV.UK bundle files keep their
  upstream names.
- **JSON form schemas:** `app/forms/<grant-slug>-<kind>-v<n>.json`
  (e.g. `ehcf-application-v1.json`, `ehcf-assessment-v1.json`). Lowercase,
  hyphen-separated, versioned from day one.
- **Grant config:** `seed/grants/<grant-slug>.json`. Same slug everywhere.
- **Tests:** `tests/test_<module>.py`, one per module under test. Shared
  fixtures in `tests/conftest.py`.
- **Ideas and decisions:** drop into `ideas/` using the timestamp prefix
  from `ideas/README.md`. Don't edit someone else's idea file — write a new
  one that references it.

### 3. Python code style

- **Python 3.12+**, type hints on all new function signatures and public
  attributes. Internal locals don't need annotations unless non-obvious.
- **Formatting:** 4-space indent, PEP 8, double-quoted strings. Keep lines
  under ~100 chars; wrap long expressions with parentheses, not backslashes.
- **Imports:** stdlib → third-party → local, blank line between groups. No
  wildcard imports.
- **Docstrings:** only for modules and for functions whose behaviour isn't
  obvious from the name + types. One-line triple-quoted is fine; full
  Google/Numpy style is overkill today.
- **No comments restating the code.** Comment the *why* when a choice is
  non-obvious (e.g. "weight applied as percentage of max, not raw score").
- **Errors:** raise specific exceptions at boundaries (input validation,
  DB constraints). Don't wrap internal calls in try/except to mask bugs.
  Let Flask's error handling surface them in dev.
- **No I/O in pure helpers.** `scoring.py`, validators, and schema walkers
  stay pure — they take data in, return data out. DB and filesystem access
  belong in blueprints or a thin persistence layer.

### 4. Flask patterns

- **App factory** (`create_app()`) in `app/__init__.py`. No module-level
  `app = Flask(__name__)`. Extensions initialised against the app inside
  the factory.
- **Blueprints per concern**, registered in the factory. URL prefixes:
  `/` (public), `/auth`, `/apply`, `/assess`. Never cross-import blueprint
  route functions — share via models or helper modules.
- **Route naming:** `snake_case` Python function names map to kebab-case
  URL paths (`def application_review` → `/apply/<id>/review`). `url_for`
  always; never hand-build a URL.
- **Session-based auth** via Flask-Login. Every non-public route is gated
  with `@login_required` and, where relevant, a role check decorator
  (`@applicant_required`, `@assessor_required`). Write the decorators
  once, in `app/auth.py`, reuse everywhere.
- **CSRF on every POST.** Flask-WTF for login/register/scoring forms gives
  this for free. For JSON-driven applicant pages, render a CSRF token
  into the page and validate it in `forms_runner.py`.

### 5. Data patterns

- **One place for grant-specific truth:** `grants.config_json`. Read it,
  don't duplicate it. If you find yourself about to copy a weight or a
  threshold into Python, rewrite the call site to read from config.
- **One place for form shape:** `forms.schema_json`. The form runner walks
  this; views never know what fields exist. Adding a field = editing JSON,
  not Python.
- **Status enums are centralised.** Define `ApplicationStatus` once in
  `models.py`; import it everywhere. Same for `AssessmentRecommendation`,
  `UserRole`. No stringly-typed status checks in views.
- **IDs are strings where they cross the JSON boundary** (criterion IDs,
  field IDs, page IDs). Numeric DB IDs stay inside SQLAlchemy.
- **Migrations:** defer Alembic until the schema settles; until then,
  destructive resets via `seed.py` are fine. Once Alembic is in, every
  model change ships with a migration in the same PR.

### 6. JSON schema & grant config contracts

These shapes are **cross-stream contracts** — if you change them, announce
it and update every consumer in the same commit.

- **Form schema:** `{id, version, pages: [{id, title, fields: [{id, type,
  label, required, ...}]}]}`. Field `type` is one of: `text`, `textarea`,
  `radio`, `checkbox`, `select`, `number`, `currency`, `date`, `file`. New
  field types need a runner handler *and* a macro.
- **Grant config:** `{slug, name, status, eligibility: [...], criteria:
  [{id, label, weight, max, auto_reject_on_zero}], award_ranges: {...},
  timeline: {...}}`. Weights sum to 100.
- **Answers payload:** `{page_id: {field_id: value}}`. Drafts and
  submissions use the same shape — `status` distinguishes them.
- **Scores payload:** `{criterion_id: int}` and notes `{criterion_id:
  str}`. Keys must match `criteria[].id` exactly.

### 7. Templates (GOV.UK)

- Always extend `base.html`. Put page-specific `<title>` in a `{% block
  title %}`; never inline a new `<html>` tag.
- Use GOV.UK macros for inputs, buttons, error summaries. Don't write raw
  `<input class="govuk-input">` — it drifts from the design system on
  upgrade.
- Error summary at the top of any form page on validation failure; the
  runner provides one, reuse it.
- No inline CSS or JS. If styling is needed beyond GOV.UK defaults, add
  to a single `app/static/app.css`.

### 8. Tests

- Every merged phase slice ships with at least **one smoke test** exercising
  the happy path end-to-end. Failure cases come later.
- Use `pytest` + Flask's `test_client`. Fixtures for `app`, `client`, a
  seeded applicant user, a seeded assessor user — all in `conftest.py`.
- Test data: reuse the EHCF seed; don't invent parallel fixtures unless
  a test specifically needs a shape EHCF doesn't have.
- Don't test framework code (that Flask routes work, that SQLAlchemy
  saves). Test *our* logic: scoring math, eligibility rules, form
  validation, status transitions.

### 9. Commits, branches, PRs

- **Branch per stream/task**, short-lived, merged to `main` the same day.
  No long-running feature branches.
- **Commit messages:** imperative mood, under 72 chars, e.g.
  `add applicant dashboard skeleton`, `read scoring weights from grant
  config`. Body only if the *why* isn't obvious.
- **One logical change per commit.** If you did two things, make two
  commits.
- **PRs are small.** A PR that touches >10 files or >400 lines of
  non-generated code should be split unless it's seed/migration data.
- Never push to `main` directly; never force-push a shared branch.

### 10. When to stop and ask

Pause and ask the team / user before:

- Introducing a new dependency (anything not already in `pyproject.toml`).
- Changing a cross-stream contract (schema shape, grant config keys,
  status enum, DB column types).
- Deleting or renaming a file that another stream imports.
- Adding a feature that isn't in the current phase of `PLAN.md`.
- Shipping anything that makes `main` not boot or `pytest` not pass.

For anything else: decide, do, commit, move on.

### 11. What "done" looks like for a Claude task

Before reporting a task complete, Claude must:

1. Have the app boot (`flask --app app run`) without import errors.
2. Have `pytest` pass (or state explicitly which tests were added/skipped
   and why).
3. Have touched only files within the task's stream (or have flagged the
   cross-stream edit and why it was necessary).
4. Have updated `PLAN.md` if a feature from the catalogue is now done,
   partially done, or consciously punted.
5. Have a commit message that names the phase/stream touched.

If any of those can't be satisfied, say so plainly — "I got X working but
Y is broken" is more useful than a green-tick summary that hides the gap.
