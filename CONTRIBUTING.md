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
    validate_page, merge_page_answers,
    evaluate_eligibility, EligibilityResult,
    SUPPORTED_FIELD_TYPES,
)
```

Pure functions — no Flask, no DB. See the module docstring for the schema
contract. Supported field types are frozen; adding one requires coordinating
with Stream A (template macro) and Stream D (model implications, if any).

Stream B also owns two shared Jinja templates (render from any blueprint):

- `templates/forms/page.html` — a single form page. Context:
  `{form, application, page, answers, errors, back_url, action_url}`.
- `templates/forms/summary.html` — read-only summary of all answers. Context:
  `{schema, answers, documents}`. Used by Stream A's review page and Stream
  C's application detail view.

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

## Definition of done (per PR)

Every PR, regardless of stream:

1. `uv run pytest` passes.
2. `uv run flask --app wsgi run` boots without import errors.
3. Touches only files in your stream's column above, or explicitly calls
   out the cross-stream edit and why.
4. Updates `PLAN.md` if you ticked a feature off.
5. No deps added to `pyproject.toml` without discussion.
