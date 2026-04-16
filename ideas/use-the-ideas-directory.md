# Use the ideas directory (meta)

**Author:** seeded by Claude — please argue with me
**Date:** 2026-04-16
**Status:** rough

## The idea

Before anyone writes a line of application code, we each drop our thoughts
about the grants platform into this `ideas/` directory as short `.md` / `.txt`
files. One file per idea. Name it so someone grepping can find it:
`forms-schema-shape.md`, `eligibility-checker.md`, `assessor-scoring-ui.md`,
`auth-magic-link.txt`.

Then we spend 30 minutes reading each other's files, group duplicates, and
pick a shape for v0. Only then do we start `/app`.

## Why it might be good

- Four people thinking in parallel surfaces more ideas than four people taking
  turns on a whiteboard.
- Written-down ideas are easier to compare side by side than half-remembered
  chat.
- Anyone joining later (or any future AI pair) can read the directory and
  understand what we considered and why we picked what we picked.
- Low stakes. Half-formed ideas are welcome — status field exists so we can
  mark things `rough`.

## Why it might be bad / open questions

- Risk of becoming a graveyard if we don't timebox the synthesis step. Propose:
  hard stop at 30 minutes, then one person drafts a "decisions" note.
- If everyone writes long essays we'll bog down. Keep ideas to a screen or two.
  If it needs more space, it's probably a design doc, not an idea.
- Do we delete superseded ideas, or just mark them `Status: dropped`? I'd say
  drop, don't delete — cheaper than reconstructing the argument later.
- Do we put decisions in `ideas/` too, or somewhere else (README? a new
  `decisions/` dir)? Worth deciding early.

## What it would touch

Team process only, no code. Sets up the habit for everything after.

## Concrete next step

Everyone: open a fresh file in here in the next hour and dump whatever you've
been chewing on. Don't read others' first — we want divergent thinking.
