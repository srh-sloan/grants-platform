# GrantOS — product vision and five-surface prototype

**Author:** Team (synthesised from hackathon brief, MHCLG Funding Service direction, EHCF prospectus)
**Date:** 2026-04-16
**Status:** agreed

## The idea

The strongest version of this prototype is not "an AI scoring tool for one
homelessness fund". It is a **small grants operating system** with four connected
surfaces: **grant builder**, **applicant workspace**, **assessor workbench**, and
**monitoring/portfolio dashboard**. That fits the hackathon brief, which rewards a
real user, a clear gap, and a convincing demo, and it also mirrors MHCLG's own
published direction: "Deliver grant funding" and "Access grant funding" are linked
services for internal grant teams and external recipients, built to support
reusable, end-to-end grant delivery across multiple funds.

The product name for the demo is:

> **GrantOS**
> *A reusable internal government grants platform for building forms, helping
> applicants submit stronger bids, helping staff assess faster, and generating
> monitoring plans after award.*

This aligns with MHCLG's own move toward reusable services, guided self-service
for grant teams, standardised data, and less burden on applicants and recipients.

---

## AI integration

The prototype calls a live AI model via the team's Anthropic/OpenAI API key.
The provider wrapper keeps prompts grant-agnostic (reading from `grant.config_json`)
so the same AI layer works for every grant added through the Grant Builder.

**Do not pitch the AI as an auto-award engine.** EHCF uses 7 weighted criteria,
each scored 0–3, and any criterion scored 0 means rejection. The hackathon's
casework challenge frames the opportunity as reducing repetitive information-gathering
so human judgement gets more time, not replacing judgement altogether.

The right story is **AI-assisted triage, evidence mapping, and draft scoring with
human review**, not "the system approves the best applications instantly".

Use this wording in the demo:

> **"AI-assisted rubric scoring and triage"**

Not: predictive funding likelihood, auto-approval, automated award decision,
or black-box ranking.

Six rules for the AI score:

1. **Ground it in the published rubric.** EHCF defines criteria, weights, and 0–3 scale.
2. **Separate eligibility from quality.** Eligibility is deterministic; quality scoring is AI-assisted.
3. **Show evidence, not just a number.** Every provisional score comes with cited snippets.
4. **Flag risk of a 0 score.** Any 0 means rejection in EHCF — that is especially valuable.
5. **Require human confirmation.** The assessor reviews, edits, and confirms.
6. **Capture overrides.** If the assessor changes the provisional score, store it as training data.

The real value proposition is:
**faster, more consistent first-pass assessment**, not "AI chooses who gets public money".

---

## The five prototype features

### 1. Grant Builder and Publisher

**Who:** internal grant team, policy official, content designer, programme manager.

**What:** an internal page where staff can create a new fund or round, define
objectives, eligibility rules, scoring criteria, required documents, milestone
questions, and reporting requirements, then preview and publish.

**Internal structure:** store each grant as a structured definition:
- grant metadata
- eligibility rules
- scoring rubric
- required documents
- form schema
- monitoring schema
- round status: draft / preview / published

Department staff interact with a UX-friendly Grant Builder interface to define
objectives, eligibility rules, scoring criteria, required documents, and form
fields without touching code or JSON files. The system is scalable — adding a
new grant is a UX task, not a developer task. Support **assisted onboarding**
with AI: staff can upload a prospectus to get a draft structure, then review
and publish through the same UI. This is MHCLG's direction: guided self-service,
not developer-dependent publishing.

**Challenge relevance:**
- Challenge 1: replaces static grant docs with a digital journey
- Challenge 2: turns unstructured prospectus content into structured data
- Challenge 4: makes the organisation's grant pipeline visible and reusable

### 2. Applicant Workspace with AI Pre-fill

**Who:** the charity or VCFS bid lead (see `2026-04-16-1210-user-research-product-framing.md`).

**What:** a GOV.UK-style task-list application flow with:
- eligibility check
- upload organisation documents
- draft answers pre-filled from uploaded material
- document checklist
- save-and-return
- submission confirmation

**Internal structure:** the applicant uploads documents (annual accounts,
organisation profile, prior project summary, partnership letters, LA support
letter, project plan, budget spreadsheet). The system extracts structured facts
into an **organisation profile** and **project evidence profile**, then maps
those to specific form fields. The user sees draft answers, edits them, and
confirms manually. Provenance matters: "this answer was drafted from your annual
report / project summary / uploaded project plan."

**Challenge relevance:**
- Challenge 1: digital grant application flow with save-and-return
- Challenge 2: document extraction into structured data

### 3. Assessor Workbench with Rubric Triage

**Who:** internal grant assessors, grant managers, moderation leads.

**What:** an internal queue showing:
- eligibility pass/fail flags
- document completeness
- per-criterion provisional score
- confidence level
- extracted evidence snippets
- likely "0-score risk"
- recommended next action

Example statuses: Ready for review, Missing required evidence, High risk of
rejection, Strong candidate (prioritise review), Needs moderation.

**Internal structure — two layers:**

**Layer A: deterministic rules**
- Lead organisation eligible?
- Under £5m income?
- At least 3 years' relevant delivery?
- Required letter uploaded?
- Budget uploaded?
- Capital/revenue structure valid?
- One application only?

**Layer B: rubric-grounded AI assessment**
For each scored criterion, retrieve relevant passages from the application and
attachments, return structured output:
- provisional score: 0/1/2/3
- rationale
- evidence found
- evidence missing
- confidence
- questions for assessor

**Challenge relevance:**
- Challenge 3: casework support — surface the right information quickly

### 4. KPI and Monitoring Plan Generator

**Who:** internal policy/grant teams first, then funded recipients.

**What:** once an application is shortlisted or approved-in-principle, generate
a draft monitoring pack:
- suggested outputs and outcomes
- baseline questions
- reporting cadence
- evidence types
- milestone checkpoints
- risk review points

**Internal structure:** use the grant's objectives, the applicant's proposed
activities, and a reusable indicator library to generate a structured monitoring
template. For EHCF, match applications against the fund's 3 objectives and suggest
KPI lines and review cadence.

**Challenge relevance:**
- Challenge 4: helps government know what was awarded and how delivery will be tracked

### 5. Portfolio and Capacity Dashboard

**Who:** team leader, director, programme office, grant operations lead.

**What:** one internal dashboard showing:
- active funds and rounds
- applications in each stage
- assessors' workload
- cases at risk of SLA delay
- common rejection reasons
- funding demand by objective / region / organisation type
- monitoring submissions due / overdue
- capacity hotspots

**Challenge relevance:**
- Challenge 4: operational visibility for leaders

---

## Challenge mapping summary

| Challenge | Features |
|---|---|
| **1: From PDF to digital service** | Grant Builder, Applicant Workspace, save-and-return, validation, checklist, submission confirmation, optional prospectus-to-draft-form assist |
| **2: Unlocking the dark data** | Prospectus/guidance ingestion, knowledge pack per grant, criteria extractor, reusable grant schema, evidence retrieval for assessors |
| **3: Supporting casework decisions** | Assessor Workbench, eligibility gate, criterion triage, missing evidence detection, next-best-action panel |
| **4: Knowing your own organisation** | Portfolio dashboard, assessor workload view, common failure/rework patterns, KPI monitoring setup and reporting completeness, cross-fund comparability |

---

## Pitch to judges

> We built a reusable grants platform for internal government teams. It starts
> with one real grant, EHCF, but the structure supports others. The prototype
> addresses all four hackathon challenge themes through one connected journey:
> turning grant guidance into structured config, helping applicants submit
> stronger bids, helping assessors triage consistently, and helping leaders see
> portfolio pressure and monitoring readiness.

---

## What not to build in 3 hours

- drag-and-drop WYSIWYG form builder (a structured field-based UI is sufficient)
- arbitrary perfect PDF-to-form conversion
- real vector infrastructure
- auto-award logic
- full payments workflow

The MHCLG principle: "go wide, not deep" — cover the whole journey in MVP form
before making one stage fancy.

---

## What to cut first if time slips

Cut in this order:

1. second grant creation UI
2. prospectus-to-form ingestion
3. dashboard charts (keep counts only)
4. document provenance niceties
5. Advanced AI features (monitoring plan generator, prospectus extractor) — keep pre-fill and criterion scoring as the core AI surface
6. any real file parsing beyond basic filename handling

Do **not** cut:
- submission flow
- assessor page
- provisional criterion scoring
- monitoring output
- README / demo story

---

## What it would touch

- README.md (product framing, users, challenge mapping, demo journey)
- PLAN.md (new features in catalogue, AI feature specs, build order, cut list)
- CLAUDE.md (AI patterns, monitoring model, grant builder model)
- CONTRIBUTING.md (AI feature stream, new surface areas)
- New model concepts: KpiTemplate, MonitoringPlan, KnowledgePack
- New AI wrapper module with mock fallback
