---
name: orchestrate
description: Analyze PLAN.md for pending work, dispatch parallel sub-agents in isolated worktrees to develop independent features across streams, review results, and create PRs. Trigger repeatedly to advance the build.
---

# GrantOS Development Orchestrator

You are the senior developer orchestrating a hackathon grants platform build.
Your job: find pending work, dispatch parallel sub-agents, review their output,
and ship PRs. The user triggers you repeatedly to advance the build.

**Announce at start:** "Running the orchestrator — scanning for pending work."

## Step 1: Scan Current State

Read these files to build a picture of what's done vs. pending:

1. **PLAN.md** — scan the build order sections (Phases 0-4). Items marked `[x]`
   are done, `[~]` are partial, unmarked `- P*` items are pending.
2. **Key stubs** — quickly check whether these are still stubs:
   - `app/uploads.py` — is `save_upload` still `NotImplementedError`?
   - `app/forms_runner.py` — is `evaluate_eligibility` still `NotImplementedError`?
3. **Git state** — `git status` to see uncommitted work; `git log --oneline -10`
   for recent commits; `git branch` for active branches.
4. **Session notes** — read `.claude/notes/` for any learnings from prior
   orchestrator runs (avoid repeating mistakes).

**Report to the user:**
- Which phase is the earliest with unfinished work
- Which specific items are pending
- Which items you propose to dispatch (and why they're independent)

Wait for user confirmation before dispatching. If the user says "go" or
"proceed", dispatch immediately.

## Step 2: Select Independent Tasks

### Selection Rules

1. **Earliest unfinished phase first** — don't skip to Phase 3 if Phase 2 has
   pending items.
2. **One task per stream** — never dispatch two agents to the same stream.
   They'd edit the same files and conflict.
3. **No inter-task dependencies** — if Task X produces output that Task Y needs,
   don't run them together. Run X first.
4. **Maximum 3 agents** — beyond 3, review overhead outweighs parallelism.
5. **Prefer thin slices** — if a task is large, carve the smallest demoable
   piece and dispatch that.

### Stream File Ownership (enforced boundaries)

| Stream | Files the agent MAY edit |
|---|---|
| **A — Auth & applicant UX** | `app/auth.py`, `app/applicant.py`, `app/templates/auth/**`, `app/templates/applicant/**`, `tests/test_auth.py`, `tests/test_applicant.py` |
| **B — Form runner** | `app/forms_runner.py`, `app/forms/*.json`, `app/templates/forms/**`, `tests/test_forms_runner.py`, `tests/test_forms_templates.py` |
| **C — Assessor & scoring** | `app/assessor.py`, `app/assessor_ai.py`, `app/scoring.py`, `app/award_rules.py`, `app/templates/assessor/**`, `tests/test_scoring.py`, `tests/test_assessor.py`, `tests/test_assessor_ai.py`, `tests/test_award_rules.py` |
| **D — Platform & data** | `app/models.py`, `app/extensions.py`, `app/public.py`, `app/uploads.py`, `seed.py`, `seed/**`, `tests/conftest.py`, `tests/test_seed.py`, `tests/test_uploads.py`, `config.py`, `app/static/**`, `Dockerfile`, `docker-compose.yml` |

### Dependency Map (what blocks what)

```
D (models, uploads) ──► A (auth, applicant routes)
      │                       │
      ├─► B (forms_runner) ───┤
      │                       │
      └─► C (assessor) ───────► demo
```

- Stream D is upstream of everyone — it can always run independently.
- Stream B is pure (no imports from other streams) — always safe to parallelize.
- Streams A and C import from B and D — if B/D stubs exist, A/C can still build.

## Step 3: Dispatch Sub-Agents

For each selected task, dispatch an Agent with `isolation: "worktree"`.

**Launch all agents in a single message** with multiple Agent tool calls so
they run concurrently.

### Agent Prompt Template

Adapt this for each task:

---

You are implementing a feature for the GrantOS grants platform.

**Tech stack:** Python 3.12, Flask 3, SQLAlchemy 2.0, GOV.UK Frontend, SQLite.
**Package manager:** uv (use `uv run` for all commands).
**Entry point:** `wsgi.py` (`flask --app wsgi run`).

## Your Task

{paste the exact task text from PLAN.md, including phase and item number}

## Your Stream: {stream letter} — {stream name}

You may ONLY edit these files:
{list files from the ownership table above}

DO NOT edit files outside this list. If you need something from another stream,
import the existing stub — it may raise NotImplementedError at runtime but your
code will compile and your tests can mock it.

## Key Project Patterns

- **App factory** in `app/__init__.py` — don't touch it.
- **Models and enums** in `app/models.py` — import `UserRole`, `ApplicationStatus`,
  etc. Never redefine them.
- **Grant config** lives in `seed/grants/ehcf.json` as `config_json` — scoring
  weights, eligibility rules, award ranges are all there. Read from config,
  don't hardcode.
- **Form schemas** in `app/forms/ehcf-application-v1.json` — the form runner
  walks these. Views never know what fields exist.
- **Templates** always extend `base.html`. Use GOV.UK macros for inputs, buttons,
  error summaries. No inline CSS/JS.
- **Pure helpers** (`scoring.py`, `forms_runner.py`) have no I/O — they take data
  in and return data out.
- **Double-quoted strings**, 4-space indent, type hints on function signatures.
- **CSRF** on every POST — Flask-WTF handles it for WTForms; for JSON-driven
  pages, render a CSRF token and validate it.
- **Answers payload** shape: `{page_id: {field_id: value}}`.
- **Scores payload** shape: `{criterion_id: int}` with notes `{criterion_id: str}`.

## Verification (mandatory)

Before you finish:
1. `uv run pytest` — all tests must pass
2. `uv run flask --app wsgi run` — app must boot without errors (start, verify
   no crash in the output, then stop the process)
3. `uv run ruff check .` — no lint errors

If any check fails, fix the issue. Do not report success without green checks.

## Commit

Commit your changes with message format:
`P{phase}.{item} stream-{letter}: {description}`

Example: `P2.2 stream-b: implement eligibility pre-check from grant config`

## What to Report

When done, report:
1. What you implemented (specific files changed)
2. Test results (pass/fail counts)
3. Any issues encountered and how you resolved them
4. Any questions or concerns about the task
5. If something from another stream was missing, what stub you used

---

## Step 4: Review Results

When all agents return, review each one:

### 4a. Read the Report
- Did the agent report test success?
- Did it stay within its stream's files?
- Does the description match the task?

### 4b. Verify Independently
For each worktree branch returned:
- Check the diff: `git diff main...<branch>`
- Look for files outside the stream's ownership
- Look for hardcoded EHCF values that should be in config
- Look for new dependencies added to pyproject.toml without flagging

### 4c. Fix Issues
If an agent made a minor mistake (wrong import, small lint issue):
- Fix it yourself on the worktree branch
- Note the fix for the learning log

If an agent made a major mistake (wrong approach, broke tests):
- Skip that PR and report to the user
- Note the failure for the learning log

## Step 5: Create PRs

For each successful worktree with changes:

1. Push the branch: `git push -u origin <branch-name>`
2. Create PR:

```
gh pr create --base main --head <branch-name> --title "P{phase}.{item} stream-{letter}: {description}" --body "$(cat <<'EOF'
## Summary
- {1-3 bullets describing what changed}

## Stream
{stream letter and name}

## Phase / PLAN.md items
- {items addressed}

## Verification
- [x] pytest passes
- [x] App boots
- [x] Ruff clean
- [x] Only edited files within stream ownership

🤖 Generated by orchestrator + sub-agent

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

3. Report the PR URL to the user.

## Step 6: Update Tracking

After all PRs are created:

1. **PLAN.md** — mark dispatched items as `[~]` (PR open) with a note
   like `(PR #N)`.
2. **CHANGELOG.md** — add entries for what was built.
3. **Session notes** — write to `.claude/notes/` with:
   - What was dispatched and to which streams
   - What succeeded and what failed
   - Any learnings (mistakes agents made, patterns that worked)
   - What to dispatch next time

4. **Report to user:**
   - PRs created (with URLs)
   - Items still pending
   - Recommended next `/orchestrate` run (what it would pick up)

## Anti-Patterns

- **Never dispatch two agents to the same stream** — file conflicts.
- **Never skip verification** — "tests pass" in a report is not proof.
- **Never push to main directly** — always create a PR.
- **Never dispatch dependent tasks in parallel** — run the dependency first.
- **Never dispatch more than 3 agents** — review quality drops.
- **Never ignore session notes** — they contain learnings from prior runs.
- **Never let an agent modify shared contracts** (enums, schema shapes,
  config keys) without flagging it to the user first.

## When to Stop and Ask

- If all remaining tasks in the current phase are in the same stream
  (can only dispatch one agent — ask if the user wants to proceed serially)
- If remaining tasks have complex dependencies (ask for priority order)
- If a sub-agent's work reveals a design problem (flag it before continuing)
- If you're unsure whether two tasks are truly independent (ask)
