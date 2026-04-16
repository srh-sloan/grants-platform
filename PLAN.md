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
- Form schema shape → `app/forms/ehcf-application-v1.json`
- Grant config shape → `seed/grants/ehcf.json` (validated by `seed.validate_grant_config`)
- Shared enums (`UserRole`, `GrantStatus`, `FormKind`, `ApplicationStatus`,
  `AssessmentRecommendation`) → `app/models.py`
- Static asset path → GOV.UK fonts/images served at `/assets/<path>` via
  `app.public.govuk_assets` so the prebuilt CSS resolves fonts correctly.

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
| **Auth & applicant UX** | registration, dashboards, status, review/submit | `auth.py`, `applicant.py`, dashboard templates |
| **Form runner** | JSON schema renderer, validation, drafts, conditional logic later | `forms_runner.py`, field macros, `/forms/*.json` |
| **Assessor & scoring** | queue, detail view, scoring form, engine, allocation dashboard | `assessor.py`, `scoring.py`, assessor templates |
| **Platform & data** | models, seed, grant/form config, GOV.UK Frontend, deploy | `models.py`, `seed.py`, `/static`, `config.py` |

Cross-cutting concerns (handled by whoever touches them first, committed
early to avoid merge pain):
- JSON form schema shape — must be agreed **before** form runner and seed
  start diverging. Propose: pair-write one file together in Phase 0, commit
  it, then fan out.
- Grant config shape (`criteria`, `weights`, `eligibility`, `award_ranges`) —
  same: pin in Phase 0.
- Status enum on `applications` — agreed up front so dashboards and
  assessor queue render consistently.

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
