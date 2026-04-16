# Changelog

All notable changes to the GrantOS grants platform.

## 2026-04-16 — Production readiness audit + 26 fixes (PRs #89, #90, #91)

### Security (PR #89)

- **Lazy `import anthropic`** in prospectus_parser.py — app no longer crashes when SDK absent.
- **SECRET_KEY warning** emitted in production when using insecure default.
- **File upload `as_attachment=True`** — uploaded files force download, preventing inline XSS.
- **Stored XSS fix** (PR #91) — escaped user-controlled values in GOV.UK macro `html` params.
- **403 sign-out** (PR #91) — replaced broken GET link with POST form + CSRF token.

### Data Integrity (PR #89)

- **`save_upload` flush vs commit** — Document rows stay in caller's transaction for proper rollback.
- **Cascade delete rules** on Grant→Forms/Applications, Application→Documents/Assessments.
- **Unique constraint** `(org_id, grant_id)` on Application prevents duplicates.
- **SQLite FK pragma** enabled via engine event listener.
- **DB indexes** on 6 frequently-queried FK columns.

### Assessor & Scoring (PR #90)

- **Assessment attribution** — `_get_or_create_assessment` now uses `current_user.id` (was AI user).
- **Monitoring plan guard** — checks `message.content` is non-empty before accessing `[0].text`.
- **Unflag restores status** — unflagging an application returns it to SUBMITTED.
- **Email notification URL** — fixed `/assessor/application/` to correct `/assess/` path.
- **AI score clamping** — scores from Claude validated against criterion max values.
- **Auto-reject guard** — `has_auto_reject` skips unscored criteria instead of treating as zero.

### Templates & Schemas (PR #91)

- **EHCF eligibility form** added to seed config — eligibility pre-check was silently skipped.
- **`la_endorsement` rule** changed from `"equals": true` to `"present"` — file fields now pass.
- **`operates_in_england` values** standardized to `"true"/"false"` across all forms.
- **Inline CSS replaced** with `.app-row--over-budget` class on allocation page.
- **Invalid GOV.UK classes** replaced with `app-` prefixed custom CSS (3 classes).
- **Table captions** added to 3 tables for screen reader accessibility.
- **Dead code removed** — unused imports, template vars, dead `{% if false %}` blocks.
- **Empty pages guard** — IndexError protection in applicant eligibility routes.
- **Demo seed data** — added missing `la_endorsement` to demo applications.

---

## 2026-04-16 — AI monitoring plan + critical bug fixes (PRs #72, #75)

### Added

- **Monitoring plan generator** (PR #72, Stream C) — `GET/POST /assess/<id>/monitoring`
  calls Claude to generate KPIs, milestones, risk review points from application
  answers and scores. Lazy anthropic import. Plan stored in assessment notes_json.
  Demo definition of done item 6 addressed.

### Fixed (PR #75 — 7 bugs from code audit)

- **All 8 test_assessor_ai failures resolved** — test suite now 261 passed, 0 failed.
- `assessor_ai.py`: module-level `import anthropic` moved to lazy import inside function.
- `test_assessor_ai.py`: tests now mock `ANTHROPIC_API_KEY` env var for hermeticity.
- `seed_demo_applications.py`: answers restructured from flat to page-keyed format.
- `assessor_ai.py`: hardcoded fallback email removed; skips send when unconfigured.
- `assessor.py`: `save_score()` no longer writes `None` gate keys to scores_json.
- `assessor_ai.py`: guard added for empty Claude `message.content`.
- `scoring.py`: `None` score values handled with `or 0` to prevent TypeError.

## 2026-04-16 — UX journey round 2: error pages, allocation, review (PRs #61, #62, #63)

### Fixed

- **Review page back link** (PR #61, Stream A) — moved from `govuk-button-group` to a proper `govuk-back-link` in `{% block beforeContent %}`, consistent with GOV.UK Design System pattern. Button group now only renders when submission is available.
- **Allocation row highlight + create-user hint** (PR #62, Stream C) — replaced invalid `govuk-!-background-colour-red` class (not in GOV.UK Frontend CSS) with working inline style; added inset text on admin create-user page about out-of-band password sharing.
- **Error page recovery + CSS utility** (PR #63, Stream D) — 403/404/500 error pages now have actionable recovery steps. `.app-row--over-budget` CSS class added to `app/static/app.css`.

## 2026-04-16 — P4.4 partnership schema (PR #60)

### Added

- **Local Digital partnership form** (PR #60, Stream B) — 4-page application
  form (`app/forms/local-digital-application-v1.json`) with a partnership page
  using `visible_when` conditional fields. Partner org details appear only when
  `is_partnership` is "yes". **No Python code changed** — the existing form
  runner handles partnership data without modification. 5 new tests.

### Status

- **Phase 0-4 complete.** All build plan items either merged or in PR #60.
- Test suite: 235 passed, 8 pre-existing anthropic SDK failures.

## 2026-04-16 — external validators (charity / company number lookup)

### Added

- **Pluggable external-validator framework** (`app/external_validators/`).
  Any form schema can now opt a field into live lookup against a third-party
  register by adding an `external_validator: {name, context_fields, ...}`
  block. The form runner stays pure; the blueprint calls the external layer
  only after basic required / word-limit checks pass.
- **FindThatCharityValidator** (default, no API key). Validates UK charity
  and company registration numbers against findthatcharity.uk, which
  aggregates Charity Commission E&W, OSCR, CCNI and Companies House into
  a single Organisation ID namespace (`GB-CHC-`, `GB-SC-`, `GB-NIC-`,
  `GB-COH-`).
- **CompaniesHouseValidator** (optional, key-based). Ships registered but
  reports itself as "skipped" until `COMPANIES_HOUSE_API_KEY` is set —
  proves out the pluggable pattern and gives a gold-standard fallback.
- **Feature flag** `EXTERNAL_VALIDATORS_ENABLED` — defaults `on` in
  production, `off` in `TestConfig` so existing tests keep posting
  placeholder registration numbers without hitting a network stub.
- **EHCF schema** — `registration_number` now declares
  `{"name": "find_that_charity", "context_fields": ["org_type"]}` so the
  applicant's declared org type steers which UK register is queried first.
- **Tests** — 31 new tests covering the validators, the page-level runner,
  the registry, the feature flag, and the applicant-blueprint integration
  with fake fetchers (no outbound HTTP).

### Engineering notes

- Transport errors (network, 5xx, timeout) yield a `skipped=True` result
  — we never block an applicant on a provider outage.
- Stdlib only (`urllib.request`) — no new dependencies.

## 2026-04-16

### Added — Claude Code automation suite

- **Orchestrator skill** (`/orchestrate`) — scans PLAN.md for pending work,
  dispatches parallel sub-agents in isolated worktrees (one per stream),
  reviews results, and creates PRs. Designed for repeated triggering to
  advance the build incrementally.
- **Ship skill** (`/ship`) — pre-flight checks (tests, lint, boot), branch
  creation, and structured PR opening. Enforces the PR-only workflow.
- **Verify skill** (`/verify`) — quick health check reporting tests, lint,
  boot status, and git state in a summary table.
- **Stream context skills** (`/stream-a` through `/stream-d`) — per-stream
  reference encoding file ownership, public APIs, imports, implementation
  status, and pending work. Used by the orchestrator to brief sub-agents.
- **Project settings** (`.claude/settings.json`) — pre-allowed permissions
  for pytest, ruff, flask, git, and gh commands so agents run without manual
  approval prompts.
- **CLAUDE.md** updated with automation skill documentation and orchestrator
  workflow description.

### Context

- 138 tests passing, 8 pre-existing failures in `test_assessor_ai.py`
- Core platform (Phase 0-1) fully implemented
- Phase 2 partially complete (uploads and eligibility evaluation still stubbed)
