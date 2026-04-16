# Grants Platform

A prototype grants application and assessment system. First grant onboarded: the
[Ending Homelessness in Communities Fund (EHCF)](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus)
administered by MHCLG.

The goal is a flexible core — so a second or third grant can be added without a rewrite —
but we're building the first grant end-to-end before generalising.

---

## Quick start

You need **one** of these installed:

- **[uv](https://docs.astral.sh/uv/)** (recommended — manages Python + deps for you), or
- **Docker + Docker Compose**.

Pick whichever you have. Both start from a clean clone; no other setup needed.

### Option A — uv (fastest inner loop)

```bash
# One-time: install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install deps (uv creates .venv and installs the locked versions)
uv sync

# Load EHCF grant + form into SQLite
uv run python seed.py

# Start the dev server on http://127.0.0.1:5000
uv run flask --app wsgi run --debug

# Run the tests
uv run pytest
```

That's it. `uv sync` is idempotent — re-running it after a `git pull` brings
your env back in sync with `uv.lock`.

### Option B — Docker Compose (one command, zero host deps)

```bash
# Build and start (prod-ish: gunicorn on :8000, data persisted in a Docker volume)
docker compose up --build

# Dev profile: Flask dev server with live reload on :5000, source bind-mounted
docker compose --profile dev up --build

# Tear down (keeps the volume)
docker compose down

# Nuke everything including the seeded DB and uploads
docker compose down -v
```

The container seeds the DB on first boot. Hit <http://127.0.0.1:8000/> (prod)
or <http://127.0.0.1:5000/> (dev).

### Common dev tasks

| Task | Command |
|---|---|
| Install / update deps | `uv sync` |
| Add a new dep | `uv add <package>` |
| Add a dev-only dep | `uv add --group dev <package>` |
| Run tests | `uv run pytest` |
| Run a single test | `uv run pytest tests/test_scoring.py -k weighted` |
| Lint | `uv run ruff check .` |
| Auto-fix lint | `uv run ruff check . --fix` |
| Reset the DB | `rm grants.db && uv run python seed.py` |
| Reset inside Docker | `docker compose run --rm web python seed.py --reset` |
| Shell inside the container | `docker compose run --rm web sh` |
| Health check | `curl http://127.0.0.1:8000/healthz` |

### Environment variables

Defaults work out of the box for local dev. Override via `.env` (gitignored) or
inline before the command.

| Variable | Default | Notes |
|---|---|---|
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | **Must** be overridden for anything shared. |
| `DATABASE_URL` | `sqlite:///grants.db` | Change to Postgres URL if we outgrow SQLite. |
| `UPLOAD_FOLDER` | `./uploads/` | Where applicant docs land. |

---

## Where the code lives

```
.
├── app/                          ← Flask app (factory pattern)
│   ├── __init__.py               ← create_app(), pre-registers blueprints
│   ├── extensions.py             ← db, login_manager, csrf singletons
│   ├── models.py                 ← SQLAlchemy models + shared enums (Stream D)
│   ├── public.py                 ← landing page, /healthz, GOV.UK assets (Stream D)
│   ├── auth.py                   ← login/register + role decorators (Stream A)
│   ├── applicant.py              ← /apply routes (Stream A)
│   ├── assessor.py               ← /assess routes (Stream C)
│   ├── forms_runner.py           ← JSON form runner, pure helpers (Stream B)
│   ├── scoring.py                ← weighted-total + auto-reject (Stream C)
│   ├── forms/                    ← JSON form definitions per grant
│   ├── templates/                ← Jinja templates, extends GOV.UK Frontend
│   └── static/                   ← GOV.UK Frontend CSS/JS + fonts/images
├── seed/grants/                  ← Grant configs loaded by seed.py
├── tests/                        ← pytest suite
├── wsgi.py                       ← entry point for gunicorn + flask --app wsgi
├── config.py                     ← Config / TestConfig
├── seed.py                       ← Loads grants + forms from disk into the DB
├── Dockerfile                    ← uv-based multi-stage image
├── docker-compose.yml            ← Prod + dev profiles
├── pyproject.toml                ← Project metadata, deps, ruff + pytest config
├── uv.lock                       ← Locked deps (checked in, managed by uv)
├── CLAUDE.md                     ← Working patterns for AI contributions
├── CONTRIBUTING.md               ← Stream ownership + merge-conflict avoidance
└── PLAN.md                       ← Feature catalogue + phase ordering
```

## Working in parallel

Four people, one day. **Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before you
start** — it lists which files each stream owns and the pinned cross-stream
contracts. The short version:

- **Stream A (Auth + applicant UX)** → `app/auth.py`, `app/applicant.py`
- **Stream B (Form runner)** → `app/forms_runner.py`, `app/forms/*.json`
- **Stream C (Assessor + scoring)** → `app/assessor.py`, `app/scoring.py`
- **Stream D (Platform + data)** → `app/models.py`, `seed.py`, `config.py`,
  Docker, static assets

If another stream hasn't shipped the symbol you need, import the stub — it'll
raise `501` or `NotImplementedError` at runtime but your tests still run.

## Ground rules

- **Iterative** — thin vertical slice first, then expand. Every commit leaves
  `main` runnable (`uv run flask --app wsgi run` boots, `uv run pytest` passes).
- **Modular** — stay inside your stream's files. Cross-stream contracts
  (schema shapes, status enums, URL prefixes) are pinned in Phase 0 and only
  change with team agreement.
- **Innovative** — the differentiator is the **JSON-defined, grant-agnostic**
  core. Anything that hardcodes EHCF shapes into Python is a regression.
- **MVP, not V1** — if a feature is only needed for the second grant, defer
  it. Working end-to-end beats any single feature done beautifully.

If a change can't demo by the end of your loop, it's too big — carve a
smaller slice.

## JSON forms

Non-developers can design forms without touching Python. A form is a JSON
file; the Flask app (`app/forms_runner.py`) is a generic runner over it.

```json
{
  "id": "ehcf-application",
  "version": 1,
  "pages": [
    {
      "id": "organisation",
      "title": "About your organisation",
      "fields": [
        {"id": "name", "type": "text", "label": "Organisation name", "required": true},
        {"id": "org_type", "type": "radio", "label": "Organisation type",
         "options": [{"value": "charity", "label": "Registered charity"}], "required": true}
      ]
    }
  ]
}
```

Supported field types are frozen: `text`, `textarea`, `radio`, `checkbox`,
`select`, `number`, `currency`, `date`, `file`. Adding one is a Stream B
change (new runner handler + new Jinja macro).

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 (pinned via `.python-version`) |
| Package / env manager | [uv](https://docs.astral.sh/uv/) |
| Web framework | Flask 3 |
| Database | SQLite (single file, zero-config; Postgres later if needed) |
| ORM | SQLAlchemy 2.0 via Flask-SQLAlchemy |
| Auth | Flask-Login + werkzeug password hashing |
| Forms | JSON schemas for applicant forms; WTForms for static forms (login, scoring) |
| Templates | Jinja2 + GOV.UK Frontend (vendored CSS/JS + jinja macros) |
| WSGI server | gunicorn (in Docker) |
| Container | Dockerfile using the official `ghcr.io/astral-sh/uv` binary pattern |

## Reference material

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to parallelise without merge conflicts
- [`PLAN.md`](PLAN.md) — feature catalogue, phase ordering, stream breakdown
- [`CLAUDE.md`](CLAUDE.md) — binding conventions for AI contributions
- `refs/ehcf-prospectus.md` — the first grant we're modelling
- `refs/pride-in-place-prospectus.md`, `refs/common-ground-award-prospectus.md`,
  `refs/changing-futures-lived-experience-support-grant-prospectus.md`,
  `refs/local-digital-fund-round-6-prospectus.md` — further shapes for
  stress-testing flexibility

## Hackathon resources

- [Hackathon repo](https://github.com/Version1/ai-engineering-lab-hackathon-london-2026)
- [Hackathon README](https://github.com/Version1/ai-engineering-lab-hackathon-london-2026/blob/main/README.md)
- [Open brief](https://github.com/Version1/ai-engineering-lab-hackathon-london-2026/blob/main/open-brief.md)
