# Grants Platform

A prototype grants application and assessment system. First grant onboarded: the
[Ending Homelessness in Communities Fund (EHCF)](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus)
administered by MHCLG.

The goal is a flexible core — so a second or third grant can be added without a rewrite —
but we're building the first grant end-to-end before generalising.

## Team

Hackathon, four people, iterative. Small steps, working software at the end of each step,
merge often.

## Scope (v0)

- **Grant recipients (applicants):** VCFS organisations that read the prospectus,
  check eligibility, fill in an application, attach supporting documents, submit.
- **Grant managers (assessors):** staff who view applications, score each criterion,
  leave notes, and reach a funding decision.

## Stack

Kept deliberately boring so we can ship in a weekend.

| Layer | Choice |
|---|---|
| Language | Python 3 |
| Web framework | Flask |
| Database | SQLite (single file, zero-config) |
| ORM / migrations | SQLAlchemy + Alembic (only if we need it) |
| Auth | Flask-Login + password hashing (bcrypt or werkzeug) |
| Forms | **JSON schemas** — form definitions live as JSON files, the app reads them to render and validate. This is the interface between form *design* and form *running*. |
| Templates | Jinja2. GOV.UK Frontend if we have time, plain HTML if not. |
| Deployment | TBD — local first, Render/Railway later if useful |

## Why JSON forms?

We want non-developers on the team to be able to design application and assessment forms
without touching Python. A form is a JSON file describing pages, fields, validation rules,
and conditional logic. The Flask app is a generic form runner over that JSON.

Rough shape we're aiming for:

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
         "options": ["charity", "CIO", "CIC", "CBS", "PCC"], "required": true}
      ]
    }
  ]
}
```

Exact shape is up for grabs — see `ideas/` and the first iteration.

## Repository layout (planned — not all of this exists yet)

```
/ideas              ← drop .md or .txt files here with ideas, sketches, questions
/refs               ← reference material (prospectuses, policy docs)
/app                ← Flask app (added once we've agreed a direction)
  /forms            ← JSON form definitions
  /templates
  /static
  models.py
  __init__.py
/tests
README.md
CLAUDE.md           ← longer-form context for the AI pair
```

## How we work

1. **Ideas first.** Before writing app code, everyone drops thoughts into `ideas/`
   as short `.md` or `.txt` files — one file per idea is fine. Prefix the
   filename with a timestamp (`YYYY-MM-DD-HHMM-short-title.md`) so lexical sort
   gives us chronological order and later ideas visibly follow earlier ones.
   See `ideas/README.md`.
2. **Synthesise.** We read each other's ideas, pick a shape for v0, agree the
   JSON form schema, and split the work.
3. **Iterate.** Ship the thinnest vertical slice first (one applicant can create an
   account, fill one page, save a draft), then expand.

## Getting started (once code exists)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --debug
```

The SQLite file lives at `./grants.db` by default.

## Reference material

- `PLAN.md` — feature catalogue, phase ordering, and who-builds-what-in-parallel
- `refs/ehcf-prospectus.md` — the first grant we're modelling
- `refs/pride-in-place-prospectus.md` — a second grant, to stress-test flexibility
- `refs/common-ground-award-prospectus.md`, `refs/changing-futures-lived-experience-support-grant-prospectus.md`, `refs/local-digital-fund-round-6-prospectus.md` — further shapes (small-award, multi-stage, council-led, partnership)
- `CLAUDE.md` — fuller architectural notes (may drift ahead of what's built; the README is the source of truth for what's actually agreed)

## Hackathon resources

- [Hackathon repo](https://github.com/Version1/ai-engineering-lab-hackathon-london-2026)
- [Hackathon README](https://github.com/Version1/ai-engineering-lab-hackathon-london-2026/blob/main/README.md)
- [Open brief](https://github.com/Version1/ai-engineering-lab-hackathon-london-2026/blob/main/open-brief.md)
