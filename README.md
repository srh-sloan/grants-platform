# GrantOS — Grants Platform

A reusable internal government grants platform that helps teams launch funds
faster, helps applicants submit stronger bids, helps assessors triage
consistently, and generates draft monitoring plans after award. The first
onboarded grant is the
[Ending Homelessness in Communities Fund (EHCF)](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus),
administered by MHCLG, used as a realistic seed grant for the prototype.

The goal is a flexible core -- so a second or third grant can be added without a rewrite --
but we're building the first grant end-to-end before generalising.

## The problem we're solving

Applying for a grant is hard. Applicants -- often small voluntary or community organisations
with limited capacity -- must interpret dense policy documents, understand complex eligibility
rules, and translate their work into the specific language assessors want to see. The result
is that good projects get rejected because the application was not written well, not because
the work was not fundable.

On the other side, assessors face the inverse burden: reading through large volumes of
inconsistent, free-text applications, manually cross-referencing answers against criteria,
and reconciling data spread across documents to reach a funding decision. This is slow,
cognitively draining, and introduces inconsistency.

We are building a platform that uses AI to reduce both burdens. For applicants, the system
provides guided, structured input -- helping them express what they actually do in a way that
maps cleanly to the assessment criteria. For assessors, it aggregates application data into a
clear, comparable view and uses AI-assisted scoring to surface signal from noise -- so staff
spend their time on judgement, not data wrangling.

---

## AI assessment layer

The platform uses **Claude (claude-sonnet-4-6)** to automatically assess every submitted
application. This runs immediately after the applicant clicks Submit, without any assessor
intervention.

### What it does

1. Reads the applicant's answers from `Application.answers_json`
2. Reads the grant's scoring criteria from `grant.config_json["criteria"]`
3. Sends a structured prompt to Claude asking it to score each criterion and explain its
   reasoning
4. Writes the result back to `Assessment.scores_json`, `Assessment.notes_json`,
   `weighted_total`, and `recommendation`
5. Emails `ross.mckelvie@fylde.gov.uk` (or `NOTIFY_EMAIL`) with the full result

The AI assessment is **idempotent** -- re-submitting the same application produces no
duplicate rows. It is also **non-blocking** -- if the Anthropic API is unavailable or returns
unparseable output, the submission still succeeds and the error is logged.

A synthetic system user (`ai-assessor@system.local`) is upserted automatically to satisfy
the non-nullable `assessor_id` foreign key. This account has an unusable password hash and
cannot log in.

### Assessor workflow

Once the AI assessment runs, assessors can:

1. Sign in and view the **queue** at `/assess/` -- all submitted applications with status
   and AI recommendation filters
2. Open an **application detail** at `/assess/<id>` -- see the applicant's answers alongside
   the AI scores and rationale
3. **Override scores** manually using the scoring form (one score + mandatory notes per
   criterion)
4. **Flag for moderation** -- marks the application for a second assessor review
5. **Record a decision** (fund / reject / refer) -- updates the application status and sends
   an outcome notification email to the applicant
6. View the **allocation dashboard** at `/assess/allocation` -- all applications ranked by
   weighted score with a running cumulative total against the fund budget

### Scoring model

Scores are grant-agnostic. The criteria, weights, and auto-reject rules all live in
`seed/grants/<slug>.json` under `criteria`. Changing the grant config changes the scoring
without touching Python.

```json
{
  "criteria": [
    {"id": "skills", "label": "Skills and experience", "weight": 10, "max": 3, "auto_reject_on_zero": true},
    {"id": "proposal2", "label": "Proposal -- project alignment", "weight": 30, "max": 3, "auto_reject_on_zero": true}
  ]
}
```

`weighted_total = sum(score * weight for each criterion)`. Maximum for EHCF is 300 (all
criteria scored 3, weights sum to 100).

Auto-reject: if any criterion flagged `auto_reject_on_zero` scores 0, the recommendation is
forced to `reject` regardless of the total.

This is stronger than "a grants portal" because the real pain is not merely
submitting data. It is helping a stretched organisation produce a coherent,
evidence-backed bid that matches how MHCLG actually scores and reviews
applications. MHCLG's own digital work is already moving toward reusable
funding services used across multiple funds, with a goal of making
applications and assessments simpler, quicker, and more consistent. That fits
our architecture of a flexible core with one grant implemented end-to-end first.

## Users

| User | Who they are | Core pain |
|---|---|---|
| **Applicant / bid lead** | Service manager, operations lead, CEO, or fundraising lead at a small VCFS homelessness organisation (income < £5m, 3+ years' delivery). Not a full-time grant writer — assembling the bid in the margins of a day that also includes service delivery, team coordination, and LA partnership work. | Translating a messy real-world service proposal into one coherent, high-scoring, fully compliant application — confirming eligibility, mapping to fund objectives, assembling evidence, producing milestones and budgets, securing an LA support letter, and making the whole thing hang together against 7 weighted criteria where a 0 on any criterion means rejection. |
| **Assessor / grant manager** | MHCLG staff in the VCS team, Homelessness and Rough Sleeping Directorate. Assesses applications, undertakes due diligence, determines allocations, notifies applicants, establishes funding agreements, and runs monitoring and evaluation. | Reading many applications and attachments, cross-referencing answers against criteria, reconciling data across documents, and making consistent decisions under volume pressure. |
| **Grant admin / policy team** | Internal staff who design and publish grant rounds, define eligibility rules, scoring criteria, required documents, and reporting requirements. | Configuring new funds quickly without bespoke development; ensuring consistent, reusable grant structures. |
| **Director / senior leader** | Team leader, programme office, grant operations lead who needs portfolio-level visibility. | Answering basic questions about workload, pipeline, risk, and capacity across funds — currently spread across disconnected systems. |

The **local authority homelessness or rough sleeping lead officer** is an
adjacent stakeholder (not core) — EHCF requires their endorsement letter, so a
poor applicant experience creates avoidable friction for councils too.

## Challenge relevance

The prototype addresses all four hackathon challenges through one connected
journey:

| Challenge | How we address it |
|---|---|
| **1: From PDF to digital service** | Grant Builder and Publisher; Applicant Workspace with task-list flow, save-and-return, validation, checklist, and submission confirmation; optional prospectus-to-draft-form assist. |
| **2: Unlocking the dark data** | Prospectus/guidance ingestion; knowledge pack per grant; criteria extractor; reusable grant schema and definitions; evidence retrieval for assessors from uploaded documents. |
| **3: Supporting casework decisions** | Assessor Workbench with eligibility gate, per-criterion triage, missing evidence detection, 0-score risk flags, and next-best-action panel. AI positioned as **triage and drafting support** — not autonomous decision-making. |
| **4: Knowing your own organisation** | Portfolio dashboard with application pipeline, assessor workload, common failure patterns, KPI monitoring setup, and cross-fund comparability. |

## Demo journey

The demo tells one clean end-to-end story in under 4 minutes. Seeded demo
accounts mean you can sign in directly as each user without manual sign-up:

1. **Grant Admin** logs in → publishes EHCF from the Grant Builder (or adds a second grant via the UI to prove reusability)
2. **Applicant** logs in → checks eligibility → uploads documents → sees AI-pre-filled draft answers → edits → reviews task list and checklist → submits
3. **Assessor** logs in → opens queue → sees eligibility pass/fail, missing documents, AI-assisted criterion scores with evidence snippets → overrides a score → marks ready for moderation
4. **Monitoring** — approved application generates a tailored KPI pack (outputs, outcomes, reporting cadence, milestone dates)
5. **Director** sees portfolio view: application counts, ready-for-review, missing-document count, 0-score risk count, average turnaround

## Prototype constraints

This is a hackathon prototype — scoped for demo, not production.

- **Real auth, seeded demo accounts** — Flask-Login with hashed passwords is fully implemented. The seed script creates demo accounts for an Applicant and an Assessor so the full flow can be demonstrated immediately without manual sign-up.
- **Real AI via Anthropic/OpenAI** — AI features call a live model using the team's API key. The provider wrapper keeps prompts grant-agnostic (read from config, not hardcoded).
- **SQLite only** — schema designed to move to Postgres later
- **Synthetic documents** — uploaded org profiles, budgets, and LA letters are test fixtures
- **EHCF as seed grant** — one fully demoed real grant
- **Multi-grant by design** — additional grants are added through the Grant Builder UI, a UX-friendly interface for department staff to define objectives, eligibility rules, scoring criteria, required documents, and form fields without touching code or JSON files

---

## Quick start

You need **one** of these installed:

- **[uv](https://docs.astral.sh/uv/)** (recommended -- manages Python + deps for you), or
- **Docker + Docker Compose**.

### Option A -- uv (fastest inner loop)

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

### Option B -- Docker Compose (one command, zero host deps)

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

### Environment variables

Defaults work for local dev. Override via `.env` (gitignored) or inline.

| Variable | Default | Notes |
|---|---|---|
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Must be overridden for anything shared |
| `DATABASE_URL` | `sqlite:///grants.db` | Switch to a Postgres URL for production |
| `UPLOAD_FOLDER` | `./uploads/` | Where applicant documents are stored |
| `ANTHROPIC_API_KEY` | _(none)_ | Required for AI assessment and pre-fill. Get one at console.anthropic.com |
| `NOTIFY_EMAIL` | `ross.mckelvie@fylde.gov.uk` | Recipient for AI assessment result emails |
| `SMTP_HOST` | `localhost` | SMTP server for outbound email |
| `SMTP_PORT` | `587` | Use 465 for SMTP_SSL |
| `SMTP_USER` | _(none)_ | SMTP username (optional) |
| `SMTP_PASSWORD` | _(none)_ | SMTP password (optional) |
| `SMTP_FROM` | `grants-platform@noreply.local` | Sender address for outbound email |

---

## Where the code lives

```
.
├── app/
│   ├── __init__.py               -- create_app(), pre-registers blueprints
│   ├── extensions.py             -- db, login_manager, csrf singletons
│   ├── models.py                 -- SQLAlchemy models + shared enums (Stream D)
│   ├── public.py                 -- landing page, /healthz, GOV.UK assets (Stream D)
│   ├── auth.py                   -- login/register + role decorators (Stream A)
│   ├── applicant.py              -- /apply routes (Stream A)
│   ├── assessor.py               -- /assess routes + AI assessment (Stream C)
│   ├── assessor_ai.py            -- Claude-powered auto-scoring (Stream C)
│   ├── forms_runner.py           -- JSON form runner, pure helpers (Stream B)
│   ├── scoring.py                -- weighted-total + auto-reject helpers (Stream C)
│   ├── uploads.py                -- document upload/download (Stream D)
│   ├── forms/                    -- JSON form schemas per grant
│   ├── templates/                -- Jinja templates, extends GOV.UK Frontend
│   └── static/                   -- GOV.UK Frontend CSS/JS + fonts/images
├── seed/grants/                  -- Grant configs loaded by seed.py
├── tests/                        -- pytest suite
├── wsgi.py                       -- Entry point for gunicorn + flask --app wsgi
├── config.py                     -- Config / TestConfig
├── seed.py                       -- Loads grants + forms from disk into the DB
├── Dockerfile                    -- uv-based multi-stage image
├── docker-compose.yml            -- Prod + dev profiles
├── pyproject.toml                -- Project metadata, deps, ruff + pytest config
├── uv.lock                       -- Locked deps (checked in, managed by uv)
├── CLAUDE.md                     -- Working patterns for AI contributions
├── CONTRIBUTING.md               -- Stream ownership + merge-conflict avoidance
└── PLAN.md                       -- Feature catalogue + phase ordering
```

## Working in parallel

Four streams, one day. Read [CONTRIBUTING.md](CONTRIBUTING.md) before you start.

| Stream | Owns | Key files |
|---|---|---|
| A -- Auth + applicant UX | Login, register, application journey | `app/auth.py`, `app/applicant.py` |
| B -- Form runner | JSON schema rendering, eligibility | `app/forms_runner.py`, `app/forms/*.json` |
| C -- Assessor + scoring | Queue, scoring, AI assessment, decisions | `app/assessor.py`, `app/assessor_ai.py`, `app/scoring.py` |
| D -- Platform + data | Models, seed, Docker, static assets | `app/models.py`, `seed.py`, `config.py` |

Cross-stream contracts (schema shapes, status enums, URL prefixes) are pinned in Phase 0 and
only change with team agreement.

## JSON forms

Non-developers can design forms without touching Python. A form is a JSON file in
`app/forms/`; the Flask app (`app/forms_runner.py`) is a generic runner over it.

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

Supported field types: `text`, `textarea`, `radio`, `checkbox`, `select`, `number`,
`currency`, `date`, `file`.

## Adding a second grant

1. Create `seed/grants/<slug>.json` with the grant config (eligibility, criteria, award ranges)
2. Create `app/forms/<slug>-application-v1.json` with the form schema
3. Run `uv run python seed.py` -- the grant appears in the platform automatically
4. No Python changes required

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Package manager | uv |
| Web framework | Flask 3 |
| Database | SQLite (dev) / Postgres (prod) |
| ORM | SQLAlchemy 2.0 via Flask-SQLAlchemy |
| Auth | Flask-Login + werkzeug password hashing |
| CSRF | Flask-WTF CSRFProtect |
| Templates | Jinja2 + GOV.UK Frontend Jinja macros |
| AI | Anthropic Claude API (claude-sonnet-4-6) |
| Email | Python smtplib (SMTP_HOST/PORT/USER/PASSWORD env vars) |
| WSGI server | gunicorn (in Docker) |

## Reference material

- [CONTRIBUTING.md](CONTRIBUTING.md) -- stream ownership and merge-conflict avoidance
- [PLAN.md](PLAN.md) -- feature catalogue, phase ordering, stream breakdown
- [CLAUDE.md](CLAUDE.md) -- binding conventions for AI contributions
- `refs/ehcf-prospectus.md` -- EHCF grant prospectus
- `refs/` -- further grant prospectuses for stress-testing flexibility
