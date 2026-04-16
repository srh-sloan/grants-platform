# Test data seed script

**Author:** Sarah
**Date:** 2026-04-16
**Status:** rough

## The idea

Write a `seed.py` script (or a Flask CLI command) that populates the database
with enough realistic data to demo the full system end-to-end during the
hackathon assessment. Covers all major entities: users, organisations, a grant,
applications in various statuses, and completed assessments with scores.

## Why it might be good

- Assessment criteria include showing a working system — we need data fast
  without manually clicking through every form.
- Covers happy path and edge cases in one run: draft applications, submitted
  ones, a rejected one (auto-reject from zero score), and a funded one.
- Anyone can reset to a clean demo state by re-running the script.
- Forces us to validate the data model early — if seed fails, the schema is wrong.

## Why it might be bad / open questions

- Seed data can drift from the real schema if we don't keep it updated as the
  model evolves — assign one person to own it.
- Do we seed inside a transaction and roll back on error, or truncate and
  re-insert? Prefer truncate-and-reseed for demos (idempotent).
- Should we ship seed data in the repo, or `.gitignore` the generated db?
  Seed *script* in repo, generated `.db` file gitignored.

## What it would touch

- `seed.py` (new file at repo root or `scripts/seed.py`)
- Depends on `models.py` and `config.py` being in place
- EHCF grant config JSON (can hardcode a trimmed version inline if the JSON
  files aren't ready yet)

## Interesting test cases to seed (from EHCF prospectus)

These are the subtle failure and low-score scenarios worth building in — they
make the assessor UI more interesting to demo than a pile of perfect applications.

### Auto-reject triggers (any criterion = 0)
- **Proposal Part 2 zero**: org describes genuine good work but never maps it
  to any of the three fund objectives (community support / day services /
  recovery). Easy real-world mistake.
- **Deliverability Part 1 zero**: narrative response only, no milestones or
  governance structure mentioned.
- **Skills and experience zero**: org has 3+ years of service delivery but in
  domestic abuse, not rough sleeping specifically — fails the criterion even
  though they look eligible on paper.

### Eligibility failures (blocked before scoring)
- Income just over £5m — passes casual inspection, fails on accounts.
- Profit-distributing CIC — CICs are listed as eligible but profit-distributing
  ones are explicitly excluded.
- LA endorsement letter from a housing officer rather than the
  homelessness/rough sleeping lead officer specifically.
- Organisation appears as lead applicant and as a named partner in a second
  bid — only one lead application allowed.

### Subtle low scores (1 instead of 2–3)
- **Cost and value (1)**: budget total is plausible but not itemised — assessor
  can't verify value for money.
- **Proposal Part 1 (1)**: local homelessness challenge identified, but backed
  by national statistics rather than local evidence.
- **Outcomes and impact (1)**: lists outputs (people supported) but no
  measurable outcomes (sustained tenancies, employment rates) and no mention of
  system strengthening.
- **Deliverability Part 2 (1)**: risks listed honestly but no mitigations — a
  risk register with no response plan.
- **Capital readiness (weak)**: Year 1 capital requested, planning permission
  described as "in progress" with no scheduled date — technically allowed but
  scores low on readiness evidence.

## Concrete next step

Once `models.py` and the Flask app factory exist, write `seed.py` that:
1. Creates two assessors and three applicant orgs
2. Seeds the EHCF grant with its scoring criteria
3. Creates applications covering: strong approval, borderline pass, auto-reject
   (Proposal Part 2 = 0), low-score reject (multiple 1s), and an eligibility
   failure
4. Creates completed assessments for scored applications with realistic per-criterion
   scores and notes drawn from the cases above
