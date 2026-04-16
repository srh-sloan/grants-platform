# Build Plan

What we need to build, in what order, and what can happen in parallel.

- `README.md` — what the team has agreed (stack, shape, how we work)
- `CLAUDE.md` — deeper architecture notes / AI working patterns
- `PLAN.md` (this file) — the feature catalogue and sequencing

All five prospectuses in `refs/` informed this. Changes to scope should be
reflected here; changes to tech/process in `README.md`.

## Ground rules for this plan

This plan is optimised for a **one-day, four-person hackathon** and assumes an
**iterative, modular, innovative MVP** posture:

- **Iterative** — phases are sized so each one ends in a demoable thin slice.
  Don't start phase N+1 until phase N demos; don't polish phase N once it
  demos.
- **Modular** — the parallelisation table below carves the code into four
  streams with minimal overlap. Stay in your stream; cross a stream boundary
  only via a contract already pinned in Phase 0 (schema, status enum, grant
  config).
- **Innovative** — the differentiator is the JSON-defined, grant-agnostic
  core. Any feature that would hardcode EHCF shapes into Python is a
  regression even if it ships faster today.
- **MVP** — if a row is in "v1" or "Deferred" below, it does not get built
  today. Resist scope creep mid-phase; capture the idea in `ideas/` and
  carry on.

When picking the next task: pull from the earliest unfinished phase in your
stream, smallest slice first.

---

## Core feature catalogue

Distilled from EHCF, Pride in Place, Common Ground, Changing Futures, and Local
Digital Fund. Each feature is tagged with which prospectus most visibly
exercises it, so we know which grant to seed next if we want to stress-test a
given feature.

### Applicant-facing

| # | Feature | Stressed most by |
|---|---|---|
| A1 | Browse open grants / read prospectus summary | all |
| A2 | Self-serve eligibility pre-check (rule-based gate) | EHCF, Local Digital |
| A3 | Register / sign in (Flask-Login, hashed passwords) | all |
| A4 | Organisation profile (separate from application answers) | all |
| A5 | Multi-page application form driven by JSON schema | all |
| A6 | Field types: text, radio, checkbox, textarea, select, number, currency, date, file | all |
| A7 | Per-page **save as draft** | all |
| A8 | Word-limit validation (per-question) | Changing Futures |
| A9 | Conditional logic / branching (e.g. capital → readiness checklist) | EHCF |
| A10 | Supporting document uploads (budget, LA letter, risk register, templates) | EHCF, Changing Futures |
| A11 | Partnership / lead-applicant structure (lead + partner orgs) | Local Digital (mandatory), EHCF (optional) |
| A12 | Read-only review page then submit (no withdrawal) | all |
| A13 | Applicant dashboard — status of each application | all |
| A14 | Outcome notification (in-app status + optional email) | all |

### Assessor-facing

| # | Feature | Stressed most by |
|---|---|---|
| B1 | Role-gated assessor area (not visible to applicants) | all |
| B2 | Application queue with filters (status, LA, funding type, score) | EHCF |
| B3 | Application detail view — answers + documents + scoring form side by side | all |
| B4 | Scoring form: 0–3 per criterion + mandatory notes (WTForms, static) | all |
| B5 | Data-driven weighted total from grant config | all |
| B6 | Auto-reject rule (any criterion at 0) | EHCF, Common Ground, Changing Futures |
| B7 | Multi-stage gates: Pass/Fail eligibility → scored evaluation → Pass/Fail declaration | Changing Futures |
| B8 | Panel interview stage (invite shortlisted applicants) | Local Digital |
| B9 | Moderation / second-assessor / flag for review | EHCF |
| B10 | Allocation dashboard — rank by weighted score, running total vs budget | EHCF |
| B11 | Award-size rules driven by a specific criterion score (e.g. sustainability → tier) | Common Ground |
| B12 | Conditional / scale-up award clause | Common Ground |
| B13 | Decision recording + outcome notification | all |

### Admin / platform

| # | Feature | Stressed most by |
|---|---|---|
| C1 | Grant-config-as-data (eligibility rules, criteria, weights, award ranges, timeline) | all |
| C2 | Form-definition-as-data (JSON schema per grant/stage) | all |
| C3 | Seed script (loads grants + forms from disk) | all |
| C4 | Role-based access control (applicant / assessor / admin) | all |
| C5 | Audit trail (who changed what, when — at least for submissions + scores) | all |
| C6 | Post-award reporting / annual claim forms | EHCF, Changing Futures |
| C7 | Notifications (email on status change, deadline reminders) | all |
| C8 | Admin UI for creating grants without touching JSON files | stretch |

---

## What's in v0 vs deferred

**v0 (must have, end-to-end for EHCF):**
A1, A2, A3, A4, A5 (subset — one stage), A6 (core field types only), A7, A10,
A12, A13, B1, B2, B3, B4, B5, B6, B10, B13, C1, C2, C3, C4.

**v1 (second grant + flexibility proof):**
A8, A9, A11, B7, B11, B12, C5. Pick *one* second grant (Common Ground is
cheapest — small, single-stage, non-uniform weights; Changing Futures is
next — adds word limits + Pass/Fail gates).

**Deferred (post-hackathon):**
A14 email, B8 panel interviews, B9 moderation workflow, C6 post-award, C7
email infra, C8 admin UI.

Status updates should edit this section, not add a new one.

---

## Build order

Phases gate on each other; within a phase, streams run in parallel. Each phase
ends with a demoable thin slice.

### Phase 0 — Foundations (blocker for everything else) ✅ done

Ship together, then fan out. Target: a Flask app that boots, renders a GOV.UK
page, talks to SQLite, and has seeded data.

- [x] P0.1 Flask app factory, config, `run.py`, `pyproject.toml` deps
- [x] P0.2 GOV.UK Frontend wired in (Jinja loader, base template, static assets)
- [x] P0.3 SQLite + SQLAlchemy models for `users`, `organisations`, `grants`, `forms`, `applications`, `documents`, `assessments`
- [x] P0.4 `seed.py` that loads EHCF grant config + one form schema from JSON
- [x] P0.5 Repo hygiene: `.gitignore`, `tests/` skeleton, one smoke test that boots the app

**Done when:** `flask --app run run` serves a styled landing page listing
seeded grants from the DB; `pytest` passes.

**Shipped cross-stream contracts** (change these only with a coordinated update):
- Form schema shape → `app/forms/ehcf-application-v1.json` + `app/forms_runner.py`
- Grant config shape → `seed/grants/ehcf.json` (validated by `seed.validate_grant_config`)
- Shared enums (`UserRole`, `GrantStatus`, `FormKind`, `ApplicationStatus`,
  `AssessmentRecommendation`) → `app/models.py`
- Blueprint URL prefixes: `/auth`, `/apply`, `/assess` — pre-registered in
  `_BLUEPRINT_MODULES` so streams never edit `app/__init__.py`
- Role decorators `applicant_required` / `assessor_required` → `app/auth.py`
- Pure scoring API (`calculate_weighted_score`, `has_auto_reject`, ...) →
  `app/scoring.py`
- Pure form-runner API (`list_pages`, `validate_page`, `merge_page_answers`, ...) →
  `app/forms_runner.py`
- Static asset path → GOV.UK fonts/images served at `/assets/<path>` via
  `app.public.govuk_assets` so the prebuilt CSS resolves fonts correctly.
- Stream ownership is documented in `CONTRIBUTING.md`.

**Shipped tooling:**
- `uv` for deps and `uv run` for scripts (lockfile at `uv.lock`, Python pinned
  via `.python-version`)
- `Dockerfile` + `docker-compose.yml` (prod profile with gunicorn, dev profile
  with Flask `--debug` + bind-mount)
- `/healthz` endpoint + compose healthcheck
- `ruff` linting config in `pyproject.toml`

### Phase 1 — Thinnest end-to-end slice

One applicant can register, open the EHCF application, fill one page, save,
and log back in to see their draft. One assessor can log in and see the empty
queue. No scoring yet, no uploads, no eligibility gate.

- P1.1 Auth: register / login / logout (Flask-Login, password hashing)
- P1.2 Role gating middleware (applicant vs assessor)
- P1.3 Form runner v0: render one page from JSON, validate required fields, save `answers_json` draft
- P1.4 Applicant dashboard: list my applications + their status
- P1.5 Assessor queue skeleton: list of submitted applications (empty for now)

Parallelisable once P0 lands:
- Stream A (Auth + dashboards): P1.1, P1.2, P1.4, P1.5
- Stream B (Form runner): P1.3

**Done when:** four-person demo — two applicants, two assessors — each see the
correct pages and a draft round-trips.

### Phase 2 — Applicant end-to-end

- P2.1 Multi-page form runner (next/back, page-level validation, resume where left off)
- P2.2 Eligibility pre-check page (reads rules from `grants.config_json`)
- P2.3 Document uploads to local filesystem, linked to the application
- P2.4 Review page (read-only summary of all answers + docs)
- P2.5 Submit action: locks answers, sets `submitted_at`, transitions status

Parallelisable:
- Stream A (Form runner depth): P2.1, P2.4, P2.5
- Stream B (Eligibility): P2.2
- Stream C (Uploads): P2.3

**Done when:** an applicant can complete the full EHCF application and submit
it; the row shows up in the assessor queue.

### Phase 3 — Assessor end-to-end

- P3.1 Application detail view: answers + docs rendered read-only
- P3.2 Scoring form (WTForms, fields derived from `grant.config_json.criteria`)
- P3.3 Scoring engine (`weighted_total`, `has_auto_reject` per `CLAUDE.md`)
- P3.4 Save partial scores + final submit
- P3.5 Allocation dashboard (rank by score, running total vs budget)
- P3.6 Record decision per application (fund / reject / refer)

Parallelisable:
- Stream A (Scoring UI): P3.1, P3.2, P3.4
- Stream B (Scoring engine + allocation): P3.3, P3.5, P3.6

**Done when:** the four demo applicants are scored; the allocation dashboard
shows who gets funded within the budget.

### Phase 4 — Flexibility proof (second grant)

Goal: add a second grant without writing grant-specific Python. Expect to
discover assumptions that baked EHCF shape into the code and refactor them
out.

- P4.1 Seed Common Ground Award (5 criteria, non-uniform weights, capital-only)
- P4.2 Word-limit validator in form runner (Changing Futures)
- P4.3 Conditional logic in JSON schema (EHCF capital → readiness fields)
- P4.4 Partnership / lead-applicant schema (Local Digital)
- P4.5 Multi-stage assessment: Pass/Fail eligibility + scored + Pass/Fail declaration

Pick 2–3 of these based on time remaining; P4.1 is the best starter because it
exposes the most assumptions for the least code.

---

## Parallelisation summary

After Phase 0, the four-person split stabilises roughly as:

| Stream | Owns through phases 1–3 | Main artefacts |
|---|---|---|
| **A — Auth & applicant UX** | registration, dashboards, status, review/submit | `auth.py`, `applicant.py`, `templates/auth/**`, `templates/applicant/**` |
| **B — Form runner** | JSON schema renderer, validation, drafts, eligibility eval, conditional logic later | `forms_runner.py`, `templates/forms/**`, field macros, `/forms/*.json` |
| **C — Assessor & scoring** | queue, detail view, scoring form, engine, allocation, decisions | `assessor.py`, `scoring.py`, `templates/assessor/**` |
| **D — Platform, data & uploads** | models, seed, dev fixtures, uploads, grant/form config, GOV.UK Frontend, deploy | `models.py`, `extensions.py`, `uploads.py`, `public.py`, `seed.py`, `seed/**`, `/static`, `config.py`, Docker |

All cross-stream contracts referenced below are **pinned in Phase 0** — see
`CONTRIBUTING.md` for the authoritative list. Changing any of them is a
coordinated edit across every consumer in the same commit.

---

## Parallel workstream briefs (Phases 1–3)

Each brief is self-contained: one developer can pick it up, read only the
files they own + the public APIs listed under "Imports from", and ship the
thin slice described at the top of each phase without waiting on anyone
else. If you need a symbol another stream hasn't built yet, **import it
anyway** — Phase 0 ships stubs that raise `501` or return placeholder data,
so your routes compile and your tests run.

### Workstream A — Auth & applicant UX

**Deliverable:** an applicant can register, sign in, see a list of their
applications, open a draft, click through the form, review answers, submit,
and see status updates on the dashboard.

**Owns (edit freely):**
- `app/auth.py` (replace the `/login`, `/register`, `/logout` stubs with WTForms-backed views)
- `app/applicant.py` (replace the dashboard stub; add start / form-page / review / submit routes)
- `app/templates/auth/**`
- `app/templates/applicant/**`
- `tests/test_auth.py`, `tests/test_applicant.py`

**Ships (mapped to phase plan):**
- P1.1 Register / login / logout (Flask-Login + `werkzeug.security`)
- P1.4 Applicant dashboard — "my applications" list with status tags
- P2.1 Thin wrapper routes for the multi-page form runner (lookup application, call Stream B's helpers, redirect to `next_page_id`)
- P2.4 Read-only review page using Stream B's `templates/forms/summary.html` partial and Stream D's document list
- P2.5 Submit action — validates no pending pages, sets `submitted_at`, transitions `ApplicationStatus.DRAFT → SUBMITTED`
- P3.6 visible half — outcome status tag / decision banner on the applicant dashboard once Stream C has written a decision

**Public API this stream exposes** (imports listed in `CONTRIBUTING.md`):
- `auth.applicant_required`, `auth.assessor_required`, `auth.login_required` (already pinned)
- Route names — `auth.login`, `auth.register`, `auth.logout`, `applicant.dashboard`, `applicant.start`, `applicant.form_page`, `applicant.save_page`, `applicant.review`, `applicant.submit` (use `url_for` from other streams)

**Imports from other streams (stubs already in place):**
- `forms_runner.list_pages`, `get_page`, `next_page_id`, `validate_page`, `merge_page_answers`, `evaluate_eligibility` — Stream B
- `models.{User, Organisation, Grant, Form, Application, UserRole, ApplicationStatus}` — Stream D
- `uploads.list_documents(application_id)` — Stream D (for review page)

**Done when:** an anonymous visitor registers, logs in, starts the EHCF application, saves the first page, logs out and back in, and sees the draft on their dashboard; `pytest tests/test_auth.py tests/test_applicant.py` passes.

### Workstream B — Form runner

**Deliverable:** a grant-agnostic JSON form engine: any correctly-shaped
schema renders as a multi-page applicant form with validation, draft saving,
eligibility pre-check, and a read-only summary — no Python changes required
to onboard a new form.

**Owns (edit freely):**
- `app/forms_runner.py` (pure helpers; no Flask/DB/I-O)
- `app/templates/forms/**` (page template, summary partial, one macro per field type)
- `app/forms/*.json` (schemas — new schemas land here)
- `tests/test_forms_runner.py` (exists), `tests/test_forms_templates.py`

**Ships (mapped to phase plan):**
- P1.3 Render one page from JSON + required-field validation + draft merge (already stubbed)
- P2.1 Multi-page support: `next_page_id` / `prev_page_id` helpers, error-summary component, "Back" navigation, page progress indicator
- P2.2 Eligibility pre-check: `evaluate_eligibility(rules, answers)` pure helper + eligibility form renderer (reuses page template)
- P2.4 read-only `templates/forms/summary.html` partial — Stream A includes it on the review page
- P4.2 Word-limit validator (when a second grant forces it)
- P4.3 Conditional field visibility (when EHCF capital / readiness check forces it)

**Public API this stream exposes** (pinned in `CONTRIBUTING.md`):

```python
from app.forms_runner import (
    list_pages, get_page, next_page_id, prev_page_id,
    validate_page, merge_page_answers,
    evaluate_eligibility, EligibilityResult,
    SUPPORTED_FIELD_TYPES,
)
```

Plus two templates other streams render:

- `templates/forms/page.html` — context: `{form, application, page, answers, errors, back_url, action_url}`
- `templates/forms/summary.html` — context: `{schema, answers, documents}` (documents list comes from Stream D)

**Imports from other streams:** none for the pure helpers. The page template uses GOV.UK Frontend macros directly and consumes the route action URLs built by Stream A.

**Done when:** every field type in `SUPPORTED_FIELD_TYPES` has a working macro; the EHCF application form renders, validates, and round-trips a draft answer via `merge_page_answers`; eligibility rules in `seed/grants/ehcf.json` evaluate deterministically against a dict of answers; `pytest tests/test_forms_runner.py` passes.

### Workstream C — Assessor & scoring

**Deliverable:** an assessor sees a filterable queue of submitted
applications, opens one, scores each criterion with notes, and the allocation
dashboard ranks everyone against the grant's budget.

**Owns (edit freely):**
- `app/assessor.py` (replace the `/assess/` stub; add detail, score-save, allocation, decision routes)
- `app/scoring.py` (already a complete pure module — extend only when a new grant demands it)
- `app/templates/assessor/**`
- `tests/test_scoring.py` (exists), `tests/test_assessor.py`

**Ships (mapped to phase plan):**
- P1.5 Queue skeleton (empty state + title bar)
- P3.1 Application detail view — applicant answers (via `templates/forms/summary.html` from Stream B) and documents (from Stream D) rendered read-only
- P3.2 Scoring form — WTForms fields generated from `grant.config_json.criteria` (score 0–N + required notes per criterion)
- P3.3 Scoring engine — already pure in `app/scoring.py`; just call `calculate_weighted_score` + `has_auto_reject`, persist on Assessment
- P3.4 Save partial / final — partial save writes scores_json/notes_json; final submit sets `weighted_total`, `recommendation`, `completed_at`
- P3.5 Allocation dashboard — rank by `weighted_total` desc, running sum of requested funding vs `grant.config_json.award_ranges.total_budget`
- P3.6 Decision recording — fund / reject / refer transitions `Application.status` to `APPROVED` / `REJECTED` (refer = remain under_review)
- B2 filters later (status, LA area, funding type, score) once the queue has rows to filter

**Public API this stream exposes** (already pinned):

```python
from app.scoring import (
    calculate_weighted_score, has_auto_reject,
    missing_criteria, max_weighted_total,
)
```

Route names other streams might `url_for`:
- `assessor.queue`, `assessor.detail`, `assessor.save_score`, `assessor.allocation`, `assessor.record_decision`

**Imports from other streams (stubs in place):**
- `auth.assessor_required` — Stream A
- `models.{Application, Assessment, User, ApplicationStatus, AssessmentRecommendation}` — Stream D
- `forms_runner.list_pages` + `templates/forms/summary.html` — Stream B, to render applicant answers in the detail view
- `uploads.list_documents(application_id)` + `uploads.document_url(doc)` — Stream D

**Critical independence note:** Stream C does **not** wait for Stream A/B to build the applicant-side submit flow. Stream D's dev fixtures (`conftest.py` / `seed/dev_fixtures.py`) fabricate a submitted application with realistic answers — Stream C builds against that from hour one.

**Done when:** logged in as the seeded assessor, all seeded submitted applications appear in the queue, each can be scored end-to-end, and the allocation dashboard shows ranked funding decisions against the £37m budget; `pytest tests/test_scoring.py tests/test_assessor.py` passes.

### Workstream D — Platform, data & uploads

**Deliverable:** every other stream has the data, fixtures, and file-handling
primitives it needs. No other stream should write raw SQL, invent a test
user, or touch the filesystem directly.

**Owns (edit freely):**
- `app/models.py` (additive column changes only; coordinate before renames)
- `app/extensions.py`
- `app/public.py` (landing page, `/healthz`, asset routing)
- `app/uploads.py` (new — file save, serve, authorise; owns `Document` row creation)
- `seed.py`, `seed/grants/*.json`, `seed/dev_fixtures.py` (new)
- `app/forms/*.json` **for new grants** (schemas for EHCF forms are Stream B's to extend; new-grant onboarding is Stream D's)
- `tests/conftest.py`, `tests/test_seed.py`, `tests/test_uploads.py`, `tests/test_dev_fixtures.py`
- `config.py`, `Dockerfile`, `docker-compose.yml`, `app/static/**`

**Ships:**
- P2.3 Uploads to local filesystem — `save_upload(application, kind, file_storage) → Document`, `list_documents(application_id) → list[Document]`, `document_url(doc) → str`, `serve_document(doc_id)` route (authz-gated; applicant can read their own, assessor can read any submitted)
- **Dev fixtures** (unblocks Stream C immediately): one seeded assessor, three seeded applicants, five applications covering the scenarios in `ideas/2026-04-16-1200-test-data-seed-script.md` (strong pass, borderline, auto-reject, low-score reject, eligibility fail). Exposed as pytest fixtures (`applicant_user`, `assessor_user`, `submitted_application`) and as a `python seed.py --dev` flag.
- Any additive model changes other streams need (e.g. `Organisation.la_area` for queue filters, `Document.description`). Land via a one-line PR tagged `models`.
- P4.1 Second grant — Common Ground Award: `seed/grants/common-ground.json` + `app/forms/common-ground-application-v1.json` + assessment schema. Exposes any hardcoded EHCF assumptions for the other streams to flush out.
- C5 audit trail (stretch) — `created_by` / `updated_by` / change-log on `Application`, `Assessment` transitions
- Deploy polish — prod `docker compose up` ends at a browser-visible demo URL

**Public API this stream exposes** (add to `CONTRIBUTING.md`):

```python
from app.uploads import save_upload, list_documents, document_url
```

Plus fixtures other streams use in tests:

```python
# tests/conftest.py
@pytest.fixture
def applicant_user(db, seeded_grant): ...
@pytest.fixture
def assessor_user(db): ...
@pytest.fixture
def submitted_application(db, seeded_grant, applicant_user): ...
```

**Imports from other streams:** none — Stream D is upstream of everyone.

**Done when:** `python seed.py --dev` populates a DB ready to demo end-to-end with zero manual clicking; `pytest` passes; `docker compose up` serves a browser-visible app at `:8000`.

---

## Dependency map (so nothing blocks)

```
D (models, uploads, fixtures) ──► A (auth, applicant routes) ──► demo
       │                               │
       ├─► B (forms_runner, macros) ───┤
       │           │
       │           └─► C (assessor views that include forms/summary.html)
       └─► C (assessor, scoring) ──────► demo
```

- **A imports from B and D.** Stubs for every B/D symbol are in the repo now,
  so A can build to 100% of its brief without either ever merging.
- **B imports from nothing.** Pure helpers + templates. B is trivially
  parallel.
- **C imports from A (decorator only), B (summary partial only), D (models + fixtures + uploads).** All stubs / stable.
- **D imports from nothing.** Upstream.

The **only real sequencing risk** is Stream D shipping its `conftest.py`
fixtures before Stream C starts writing assessor tests. If Stream D slips,
Stream C fabricates a local fixture in their own test file, then deletes it
in the PR that consumes D's shared one.

---

## Risks & watch-outs

- **Form runner scope creep.** Resist inventing a schema language. Start with
  a hardcoded list of field types (text, radio, checkbox, textarea, select,
  number, date, file). Add word limits and conditional logic only when a
  second grant forces it.
- **WTForms temptation for applicant forms.** Don't. `CLAUDE.md` is clear —
  WTForms is for static forms (login, scoring). Application forms are
  JSON-driven or we lose the whole point.
- **Premature abstraction.** The second grant will teach us what's actually
  shared. Don't generalise EHCF shapes until Phase 4 pushes back.
- **Merge contention on models.py.** Agree the schema in Phase 0, then owners
  only add columns within their stream's tables.
- **File uploads.** Local filesystem only for v0. If we need S3 we're already
  off-plan.

---

## Definition of done per phase

A phase is done when:
1. The slice described at the top of the phase demos end-to-end.
2. A smoke test exercises the happy path.
3. This file is updated — tick features off the catalogue, note anything we
   punted, record any decisions that contradict earlier plan entries.

A phase is **not** done just because the code is written. If it doesn't demo,
it's not done; if it demos but isn't merged to `main`, it's not done; if it's
merged but nobody else's stream can build on it, it's not done.

## MVP reminders (read before picking up work)

- **Thin slice over full feature.** One applicant, one page, one grant, one
  assessor, one score — then iterate. Full coverage is a phase 4 problem.
- **Config, not code.** If you're about to write `if grant.slug == "ehcf"`,
  stop — that belongs in `grants.config_json` or `forms.schema_json`.
- **Stub the cross-stream contract.** If your stream needs something another
  stream owns, land an empty function / fake data / TODO marker with the
  agreed signature, then unblock yourself. Don't re-implement the other
  stream's work.
- **Commit every green slice.** Small commits, often. If you've been heads-down
  for an hour without pushing, you're too deep.
- **Prefer deleting scope over delaying a phase.** Cutting a field, skipping
  a page, or hardcoding one screen is fine if it keeps the phase on track —
  flag it in this file under the phase so it doesn't get lost.
