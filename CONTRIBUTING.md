# Contributing — how to parallelise without merge conflicts

Four streams work on this repo concurrently. The foundation (Phase 0) is done.
This doc tells you **which files your stream owns**, which files are
**shared contracts** (change only with coordination), and the **public APIs**
each stream exposes to the others.

If you feel the itch to edit a file outside your stream, stop and check here
first.

---

## Stream ownership

| Stream | Owns (edit freely) | Shared with |
|---|---|---|
| **A — Auth & applicant UX** | `app/auth.py`, `app/applicant.py`, `app/templates/auth/**`, `app/templates/applicant/**` | — |
| **B — Form runner** | `app/forms_runner.py`, `app/forms/*.json` (EHCF), `app/templates/forms/**` (page, summary, field macros) | Applicant (Stream A) and Assessor (Stream C) both render via Stream B's templates |
| **C — Assessor & scoring** | `app/assessor.py`, `app/scoring.py`, `app/templates/assessor/**` | Assessor routes use `auth` decorators; detail view includes `templates/forms/summary.html` |
| **D — Platform, data & uploads** | `app/models.py`, `app/extensions.py`, `app/public.py`, `app/uploads.py`, `seed.py`, `seed/grants/*.json`, `seed/dev_fixtures.py`, `tests/conftest.py`, `config.py`, `Dockerfile`, `docker-compose.yml`, `app/static/**` | Everyone imports models + enums + fixtures; Streams A and C import `app.uploads` |

Templates that are **shared chrome** (every page uses them) live in
`app/templates/base.html` and `app/templates/partials/header.html`. These
change rarely — open a PR with the other streams tagged before editing.

## Public APIs each stream exposes

These are the only symbols other streams should import from each module. If
you need something else, add it here first and post it in the team channel.

### `app.auth` (Stream A)

```python
from app.auth import applicant_required, assessor_required, login_required
```

- `applicant_required` / `assessor_required` — route decorators. Anonymous
  users are redirected to `auth.login`; wrong-role users get a 403.
- `login_required` — re-exported from Flask-Login for uniformity.

### `app.forms_runner` (Stream B)

```python
from app.forms_runner import (
    list_pages, get_page, next_page_id, prev_page_id,
    get_page_position,   # returns (1-based position, total pages) for a page_id
    validate_page, merge_page_answers,
    evaluate_eligibility, EligibilityResult,
    format_answer,       # type-aware value formatter for summary display
    SUPPORTED_FIELD_TYPES,
)
```

Pure functions — no Flask, no DB. See the module docstring for the schema
contract. Supported field types are frozen; adding one requires coordinating
with Stream A (template macro) and Stream D (model implications, if any).

`get_page_position(schema, page_id) -> tuple[int, int]` returns `(position,
total)` where position is 1-based. Raises `ValueError` if `page_id` is not
found in the schema. Stream A uses this to pass `page_number` and `total_pages`
to `forms/page.html`.

Stream B also owns two shared Jinja templates (render from any blueprint):

- `templates/forms/page.html` — a single form page. Context:
  `{form, application, page, answers, errors, back_url, action_url,
  page_number (optional int), total_pages (optional int)}`. When both
  `page_number` and `total_pages` are provided (non-None), the template
  renders a "Page X of Y" progress indicator above the page heading.
- `templates/forms/summary.html` — read-only summary of all answers. Context:
  `{schema, answers, documents}`. Used by Stream A's review page and Stream
  C's application detail view.
- `templates/forms/eligibility_result.html` — eligibility pass/fail result.
  Context: `{result, grant, continue_url, check_url}`. `result` is an
  `EligibilityResult` (from `app.forms_runner`) with `.passed: bool`,
  `.failures: list[str]` (rule IDs that failed), and `.labels: dict[str, str]`
  (rule ID → human-readable label). `grant` is the `Grant` model. `continue_url`
  is the URL to start the application (shown only when `result.passed` is true).
  `check_url` is the URL to re-take the eligibility check.

### `app.scoring` (Stream C)

```python
from app.scoring import (
    calculate_weighted_score, has_auto_reject,
    missing_criteria, max_weighted_total,
)
```

Also pure functions. Input is always `(scores: dict, criteria: list[dict])`.

### `app.models` + `app.extensions` (Stream D)

```python
from app.extensions import db, login_manager, csrf
from app.models import (
    User, Organisation, Grant, Form, Application, Document, Assessment,
    UserRole, GrantStatus, FormKind, ApplicationStatus, AssessmentRecommendation,
)
```

- **Never re-declare status enums** in a view. Import from `app.models`.
- **Adding a column** is a Stream D change — file a one-line PR rather than
  sliding it into an unrelated feature PR.

### `app.uploads` (Stream D)

```python
from app.uploads import save_upload, list_documents, document_url
```

- `save_upload(application, kind, file_storage) -> Document` — writes the
  bytes under `UPLOAD_FOLDER/<application_id>/<kind>/<filename>` and creates
  the `Document` row. Raises `UploadRejected` on size / MIME violations.
- `list_documents(application_id) -> list[Document]` — safe for both
  applicant review pages and assessor detail views.
- `document_url(doc) -> str` — URL for the authz-gated download route.

Streams A and C import these; nobody else touches `UPLOAD_FOLDER` or writes
`Document` rows by hand.

### `tests.conftest` fixtures (Stream D)

```python
# Available to every test module
app, client, db, seeded_grant,          # already shipped in Phase 0
applicant_user, assessor_user,          # D ships alongside auth work
submitted_application,                  # D ships alongside uploads work
```

Stream C builds the scoring UI against `submitted_application` without
waiting for Streams A/B to finish the applicant-side submit flow.

## Cross-stream contracts (coordinate before changing)

Change any of these and every stream breaks. Propose in `#grants` first.

| Contract | Owned by | Location |
|---|---|---|
| Form schema shape (pages/fields) | Stream B | `app/forms/ehcf-application-v1.json` + `app/forms_runner.py` docstring |
| Grant config shape (criteria/eligibility/etc) | Stream D | `seed/grants/ehcf.json` + `seed.py::validate_grant_config` |
| Eligibility rule shape (`type`, `value`/`values`) | Stream D (shape) + Stream B (evaluator) | `seed/grants/ehcf.json` + `app/forms_runner.py::evaluate_eligibility` |
| Status enums | Stream D | `app/models.py` |
| Blueprint URL prefixes (`/auth`, `/apply`, `/assess`, `/uploads`) | Whoever owns the blueprint | `app/<blueprint>.py` |
| Answers payload shape `{page_id: {field_id: value}}` | Stream B | `app/forms_runner.py::merge_page_answers` |
| Scores payload shape `{criterion_id: int}` | Stream C | `app/scoring.py` docstring |
| Uploads API (`save_upload`, `list_documents`, `document_url`) | Stream D | `app/uploads.py` |
| Shared templates `forms/page.html`, `forms/summary.html` context | Stream B | `app/templates/forms/*.html` |
| Shared test fixtures | Stream D | `tests/conftest.py` |

New blueprints get added to `_BLUEPRINT_MODULES` in `app/__init__.py`. Touch
nothing else in the factory.

## Getting unblocked

- **Need a symbol another stream hasn't built yet?** Import it anyway — the
  stub will raise `501` or `NotImplementedError`. Your route and tests can
  still compile. Open a PR on the stub with the shape you need; don't
  reach across and write it yourself.
- **Need a new column?** Open a one-liner PR tagged `models` so Stream D can
  ack before it lands. Never land silent schema changes.
- **Need a new field type in the form runner?** Stream B adds a handler in
  `forms_runner.py` and a Jinja macro under `templates/forms/`. Co-ordinate
  in Slack before starting — it's a contract change.

## Hackathon requirements

These are the non-negotiables for what we ship today.

### Working interface — usable, accessible, GOV.UK styled

- The app must be navigable end-to-end by a real user, not just runnable by a developer.
- Follow GOV.UK Frontend conventions throughout: use the provided macros and components, don't roll bespoke HTML where a GOV.UK component exists.
- Remove the GOV.UK crown logo — this is a prototype, not an official government service.
- All pages must meet basic accessibility standards: correct heading hierarchy, visible focus states, form labels associated with inputs, error messages linked to fields.
- Error states and empty states must be handled — no raw stack traces or blank pages reaching the user.

### Dependency hygiene — blueprint for keeping packages current

- Before upgrading any package, check the release notes for breaking changes.
- **GOV.UK Frontend**: download the new `govuk-frontend.min.css` and `govuk-frontend.min.js` from the [releases page](https://github.com/alphagov/govuk-frontend/releases), replace the files in `app/static/`, and smoke-test the header, footer, and at least one form page. Check the changelog for any macro API changes that affect our Jinja templates.
- **Python deps**: run `uv sync` after editing `pyproject.toml`. Commit both `pyproject.toml` and the updated `uv.lock` in the same PR. Tag it `deps` in the title.
- Never upgrade a dep as a side-effect of a feature PR — keep it a separate commit or PR so it's easy to revert.

### Use agents, skills, and AI tools

- AI is a first-class tool today, not a last resort. Use it for: drafting form schemas, generating seed data, writing scoring logic, producing boilerplate templates.
- Prefer Claude Code skills (`/commit`, `/simplify`, `claude-api`) over writing the equivalent manually.
- Where the app itself calls an AI (e.g. assessment assistance, application guidance), use the Anthropic SDK and structure prompts to be grant-agnostic — the prompt should read from grant config, not contain hardcoded EHCF references.
- Log or surface AI-generated content clearly in the UI so assessors know when a suggestion came from a model.

### Show domain knowledge — context and expertise in the product

- The UI copy should reflect grant sector language: use terms like "applicant organisation", "funding criteria", "LA endorsement", "revenue vs capital funding" correctly.
- Eligibility checks should show the user *why* they don't qualify, not just that they don't — reference the specific rule.
- Assessment screens should display the grant's scoring guidance alongside the score input, drawn from `config_json`, so assessors don't need to consult the prospectus separately.
- Where we summarise an application for an assessor, the summary should highlight the fields that carry the most scoring weight — again, derived from config, not hardcoded.

### AI features — positioning and implementation

- **AI is triage and drafting support, not an auto-award engine.** Frame every
  AI feature as "AI-assisted" with human confirmation, never "AI decides."
- Every AI feature calls a live model via the team's Anthropic/OpenAI API key
  through a provider wrapper. Structure prompts to be grant-agnostic — prompts
  read from `grant.config_json`, not hardcoded EHCF references.
- **Show provenance.** Pre-filled answers must say where the suggestion came
  from ("drafted from your annual report"). Provisional scores must show
  evidence snippets and confidence level.
- **Capture assessor overrides.** If an assessor changes a provisional AI
  score, store the original and the override — useful as training data later.
- Log or surface AI-generated content clearly in the UI so assessors know
  when a suggestion came from a model.

### Monitoring and dashboard surfaces

- The monitoring plan generator (feature F1 in `PLAN.md`) produces a **draft**
  KPI pack — suggested outputs, outcomes, baselines, reporting cadence,
  evidence types, milestones, and risk review points.
- The portfolio dashboard (F2, F3) shows operational counts only — do not
  build complex charts. Application pipeline, assessor workload, missing
  documents, 0-score risks, and average turnaround are the priority views.

## Definition of done (per PR)

Every PR, regardless of stream:

1. `uv run pytest` passes.
2. `uv run flask --app wsgi run` boots without import errors.
3. Touches only files in your stream's column above, or explicitly calls
   out the cross-stream edit and why.
4. Updates `PLAN.md` if you ticked a feature off.
5. No deps added to `pyproject.toml` without discussion.
