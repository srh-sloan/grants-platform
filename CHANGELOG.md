# Changelog

All notable changes to the GrantOS grants platform.

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
