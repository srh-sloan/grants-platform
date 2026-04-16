# Primary user research — VCFS bid lead

**Author:** Team (synthesised from EHCF prospectus, webinar, Homeless Link evidence, hackathon brief)
**Date:** 2026-04-16
**Status:** agreed

## The idea

Do not design for a generic grant applicant. Design for a **specific person**: the bid lead at a
small or mid-sized VCFS homelessness organisation trying to turn a real service proposal into one
complete, competitive, compliant EHCF application.

This is the most defensible primary user for the prototype and the one who will make the demo land.

---

## Who they are

The bid lead is often a service manager, operations lead, CEO of a small charity, or fundraising
lead — frequently wearing several of those hats at once. They are **not** a full-time grant writer.

EHCF targets VCFS organisations in England with:
- Annual income under £5,000,000
- At least 3 years' relevant delivery experience
- One application per organisation (may combine multiple projects, capital + revenue, partners)

That "one application" constraint is important: this user is coordinating organisational knowledge,
finance, delivery, partnerships, and compliance — not just filling in fields.

---

## What their day looks like

They are running or supporting real homelessness services. Sector evidence from the 2024 Homeless
Link review makes their environment clear:

- 81% of accommodation projects had to turn people away — needs too high or complex
- 79% of day centres saw more first-time homelessness
- 60% of day centres rely mainly on fundraising, grants, and philanthropy
- 46% of day centres reported risk of closure from financial pressure

They are assembling a bid in the margins of a day that also includes service delivery, team
coordination, LA partnership work, finance/budget discussions, and safeguarding. The EHCF webinar
confirms this: strong bids require track record, partnership working, alignment to local need,
credible delivery plans, realistic budgets, governance, risk management, and clear outcomes. That
is a cross-organisational coordination task, not a form-filling task.

---

## What specific task is painful today

Translating a messy real-world service proposal into a coherent, high-scoring, fully compliant
application. For EHCF this means:

1. Confirming eligibility
2. Mapping their project to one or more of EHCF's three objectives
3. Assembling locally focused evidence of need (not national statistics)
4. Explaining skills and prior experience with rough sleeping specifically
5. Producing milestones, governance structure, risk register
6. Uploading an itemised Excel budget broken down by year and quarter (capital + revenue separate)
7. Uploading a project plan (Gantt chart or equivalent)
8. Securing and uploading a local-authority support letter from the homelessness/rough sleeping lead
9. Making the whole thing hang together as one coherent proposal

The scoring design sharpens this pain: 7 weighted criteria totalling 300 points, any criterion
scoring 0 = auto-rejection. The two biggest weights are Proposal Part 2 (30%) and Deliverability
Part 1 (25%). Applicants are not just trying to submit — they are trying to optimise narrative,
evidence, and attachments against an implicit scoring model they may not fully understand.

There is also a coordination burden outside the form: only one application per organisation,
the LA support letter must be uploaded as a PDF (even though an email is acceptable), and the
budget template has a specific required structure. That forces internal consolidation, external
chasing, document wrangling, and last-minute risk.

---

## What they would notice if the system were better

**1. Clarity** — early visibility of whether they are eligible, what evidence is required, and
whether their idea actually fits the fund's objectives and scoring logic.

**2. Less duplication** — the system reuses core organisational data rather than requiring them
to restate the organisation, project, risks, and outcomes in disconnected sections. MHCLG's own
funding-service team flagged this as a known pain: applicants want access to old application data
to reuse in new applications.

**3. Confidence** — knowing what is missing, what is weak, and whether the application is
internally coherent before submission.

**4. Administrative relief** — no ad hoc spreadsheets, no version-control chaos, no manual
checking that the project plan, budget, and narrative match.

**5. Post-submission reassurance** — reference number, clear acknowledgement, status visibility,
structured confirmation rather than a vague "sent something somewhere" message.

---

## Secondary user

**MHCLG grant assessor / grant manager** in the VCS team, Homelessness and Rough Sleeping
Directorate. They assess applications, undertake due diligence, determine allocations, notify
applicants, establish funding agreements, and run monitoring and evaluation.

Their pain maps to Challenge 3: reading many applications, cross-referencing answers against
criteria, reconciling data across documents, making consistent decisions under volume pressure.

Adjacent stakeholder (not core): the **local authority homelessness or rough sleeping lead
officer** who must provide the endorsement letter. A poor applicant experience creates avoidable
friction for councils too.

---

## Product framing this implies

The strongest demo pitch is:

> **"A bid-prep and assessment-ready grants service for small VCFS homelessness organisations
> applying to EHCF."**

This is stronger than "a grants portal" because the real pain is not submitting data — it is
helping a stretched organisation produce a coherent, evidence-backed bid that matches how MHCLG
actually scores and reviews applications. The department's own digital work is already moving
toward reusable funding services used across multiple funds, with a goal of making applications
and assessments simpler, quicker, and more consistent across programmes. That fits the GrantOS
architecture of a flexible core with one grant implemented end-to-end first.

The product name for the demo is **GrantOS** (see
`2026-04-16-1215-grantos-product-vision.md` for the full five-surface product vision).

The primary user story is applicant-side. The secondary value story is assessor-side. The demo
arc is:

1. Understand the prospectus (eligibility check, objectives map)
2. Draft a strong application (AI pre-fill from uploaded docs)
3. Validate completeness and fit (checklist, missing evidence warnings)
4. Hand assessors a more structured, comparable case (rubric triage, evidence snippets)

### Bottom-line framing for judges

If you want the sharpest answer to the five hackathon questions:

* **Primary user:** the bid lead inside a small VCFS homelessness organisation applying to EHCF.
* **Their day:** running or supporting real homelessness services while also coordinating finance,
  evidence, partnerships, and governance under funding pressure.
* **Painful task:** turning a messy real-world project into one coherent, high-scoring EHCF
  application with the right attachments, evidence, and local-authority backing.
* **What better looks like:** early eligibility clarity, guided drafting against criteria,
  attachment/completeness checks, internal consistency, and confidence before submission.
* **Secondary user:** the MHCLG assessor who needs structured, comparable, assessable
  applications, with the local-authority endorser as an important adjacent stakeholder.

The strongest prototype concept is not just "an online form". It is **an applicant-side bid-prep
assistant plus assessor-ready structured application flow for EHCF-style government grants**.

---

## NCVO sector evidence (additional context)

NCVO's "Power of Small" report says application and reporting processes are often
disproportionately complex for small charities and should be simplified and right-sized.
This validates the core pain point — even beyond EHCF.

MHCLG's own funding-service team has explicitly said one of the next pain points they were
exploring was giving applicants access to old application data so they can reuse it in new
applications — directly supporting the "less duplication" benefit above.

---

## Useful public artefacts for demo and test fixtures

| Artefact | Use | Source |
|---|---|---|
| EHCF prospectus (GOV.UK) | Rules, criteria, objectives, required documents | [GOV.UK](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus) |
| EHCF webinar PDF (Housing Justice) | "Good/bad application" guidance, attachment expectations, scoring emphases | [Housing Justice](https://housingjustice.org.uk/wp-content/uploads/2026/02/MHCLG-Ending-Homelessness-in-Communities-Fund-Webinar.pdf) |
| Official budget template (prospectus link) | File upload + validation test fixture; itemised by year and quarter | [Linked from prospectus](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus) |
| LA support letter rules (FAQ) | Attachment handling: email acceptable, must upload as PDF | [Prospectus FAQ](https://www.gov.uk/guidance/ending-homelessness-in-communities-fund-prospectus) |
| Homeless England database (Homeless Link) | Synthetic organisations and local service context (~1,500 projects) | [Homeless Link](https://homeless.org.uk/homeless-england/) |
| DPIF full question list (Access Funding portal) | Structural analogue for JSON form design (not the EHCF form) | [Access Funding](https://apply.access-funding.communities.gov.uk/all_questions/DPIF/R2) |
| National rough sleeping statistics (GOV.UK) | "Evidence of need" text for synthetic applications | [GOV.UK](https://www.gov.uk/government/statistics/rough-sleeping-snapshot-in-england-autumn-2025/rough-sleeping-snapshot-in-england-autumn-2025) |
| 2024 Support to End Homelessness review | Survey evidence from 204 accommodation providers and 40 day centres | [Homeless Link](https://homeless.org.uk/knowledge-hub/2024-review-of-services-addressing-single-homelessness-in-england/) |
| National Plan to End Homelessness | Policy story — EHCF as part of the plan | [GOV.UK](https://www.gov.uk/government/publications/a-national-plan-to-end-homelessness/a-national-plan-to-end-homelessness) |
| EHCF application portal page | Real service framing and timing | [Access Funding](https://apply.access-funding.communities.gov.uk/funding-round/EHCF/APPLY) |
| Project-plan upload requirement (webinar) | Second attachment type beyond budget; Gantt chart or equivalent | Webinar PDF |
| Other public grant examples | Prove multi-grant extensibility (SHIF, COF, Pride in Place, Changing Futures) | [Access Funding](https://apply.access-funding.communities.gov.uk) |

**Caveat:** the full EHCF application question list is not publicly indexed. Use the prospectus
and webinar to reconstruct the shape. The DPIF question list is a useful analogue for
structure but is not the EHCF form.

---

## Background facts for the pitch narrative

- EHCF is a 3-year fund (2026–2029), part of the National Plan to End Homelessness
- £37m total; supports 100+ VCFS organisations; targets 60,000+ people per year
- Rough sleeping rose to 8.2 per 100,000 in England in 2025 (autumn census: 4,793 people)
- 43% of rough sleepers on a single night were in London and South East
- Homeless Link database: ~1,500 homelessness projects across England

These give a clear policy story for why a better applicant and assessor experience matters.

---

## What it would touch

- Primary user persona for README, PLAN.md, demo script, judging answers
- Applicant journey design (task list, eligibility check, pre-fill, checklist)
- Assessor workbench design (evidence surfacing, rubric triage)
- Test data / seed scenarios (realistic VCFS organisation profiles)
