# Grants Platform

A prototype grants application and assessment system. First grant onboarded: the
[Ending Homelessness in Communities Fund (EHCF)](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus)
administered by MHCLG.

The goal is a flexible core — so a second or third grant can be added without a rewrite —
but we're building the first grant end-to-end before generalising.

## Team & shape of work

**One-day hackathon, four people, iterative MVP.** Our non-negotiables:

- **Iterative** — ship the thinnest vertical slice first, then grow outwards.
  Every commit should leave `main` runnable. No long-lived branches.
- **Modular** — four people working in parallel, so the code must split along
  clean seams (auth, form runner, assessor/scoring, platform/data). Cross-stream
  contracts (schema shape, status enum, grant config keys) are pinned in
  Phase 0 and not silently changed.
- **Innovative** — the point of the day isn't CRUD; it's proving that a
  JSON-defined, grant-agnostic core can absorb a second (and third) grant
  without a rewrite. Optimise choices for that demo.
- **MVP, not V1.** If a feature is only needed for the second grant, defer it.
  If a feature is polish, defer it. "Working software end-to-end" beats "one
  feature done beautifully" every time today.

If you can't demo a change by the end of your current loop, it's too big —
carve a smaller slice.

## Scope (v0)

- **Grant recipients (applicants):** VCFS organisations that read the prospectus,
  check eligibility, fill in an application, attach supporting documents, submit.
- **Grant managers (assessors):** staff who view applications, score each criterion,
  leave notes, and reach a funding decision.

## Stack

Kept deliberately boring so we can ship in a day.

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
   JSON form schema and the grant config shape, and split the work along the
   four streams in `PLAN.md`.
3. **Iterate in thin slices.** Ship the thinnest vertical slice first (one
   applicant can create an account, fill one page, save a draft), demo it,
   then expand. Each phase in `PLAN.md` ends with a demoable slice — don't
   start the next phase until the current one demos.
4. **Merge often.** Small PRs, trunk-based. If you're blocked waiting on
   another stream, stub the contract (an empty function, a fake status) and
   keep moving.

## Working with Claude (AI pair)

Claude is a fifth pair of hands today. To keep its output consistent across
all four streams, every prompt should be able to assume Claude has read:

- `README.md` — what we agreed (this file)
- `PLAN.md` — what to build next, in which stream
- `CLAUDE.md` — the working patterns and conventions to follow

**`CLAUDE.md` contains the binding style/pattern rules for AI contributions.**
If Claude's output contradicts a rule there, that's a bug — fix the output,
not the rule (unless the team agrees the rule is wrong, in which case change
it once, in `CLAUDE.md`, so every future prompt picks it up).

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
