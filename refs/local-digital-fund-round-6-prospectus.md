# Local Digital Fund — Round 6 Prospectus

> Source: https://www.localdigital.gov.uk/fund/local-digital-fund-prospectus-round-6/
> Retrieved: 2026-04-16
> Note: Round 6 is a historic round (applications closed 24 November 2022, 17 projects awarded £2,016,325 in March 2023). Included here as a second shape of grant — **councils not VCFS applicants, agile project phases (Discovery / Alpha / Beta), panel interviews** — to stress-test the platform's flexibility.

---

## Overview

The Local Digital Fund, administered by the Ministry of Housing, Communities and Local Government (MHCLG), supports digital service transformation across English local government in a collaborative, joined-up way. The fund aims to make council services "safer, more resilient and cheaper to run", and to break dependence on inflexible, expensive technology that doesn't join up effectively.

Round 6 invited councils to propose **Discovery**, **Alpha**, and **Beta** projects following the GDS-style agile delivery phases.

---

## Eligibility Requirements

**Lead applicant:**
- Must be a local authority in England
- Must be able to receive Section 31 grant payments
- Must be a Local Digital Declaration signatory (or become one before the application deadline)

**Partnership requirement:**
- Each proposal must have a lead council and **at least two other councils as partners**
- Partner councils must also be Local Digital Declaration signatories before the deadline
- Applications without the required partnership structure are ineligible

---

## Funding Structure

Funding amounts depend on project phase:

| Phase | Purpose | Max funding |
|---|---|---|
| Discovery | Understand a problem area, its cost to taxpayers and impact on the public; propose ways to move forward | Up to £100,000 |
| Alpha | Available to projects that can evidence a completed discovery; prototype and test approaches | Up to £180,000 |
| Beta | Take the best idea from alpha and build it for real, rolling out to real users while minimising risk | Up to £350,000 |

Round 6 total awarded: **£2,016,325 across 17 council-led agile projects**.

---

## Timeline

| Milestone | Date |
|---|---|
| Application form templates available to councils | 13 October 2022 |
| Web application forms available | 17 October 2022 |
| Application deadline | 5:30pm, 24 November 2022 |
| Panel interviews (selected applicants) | 6–7 December 2022 |
| Funded projects announced | March 2023 |
| Project delivery begins | March 2023 onwards |

---

## Assessment Criteria

Project applications are assessed against three criteria:

### 1. Strategic fit
- How projects demonstrate making local government services **safer, more resilient, and/or cheaper to run**
- How learnings and products can be **reused by others** beyond the end of the project

### 2. Deliverability
- How projects will be financially resourced and delivered by the team **in line with agile principles**
- Comprehensive plans to mitigate risks
- Effective engagement with partners and stakeholders

### 3. Value for money
- Potential level of savings from the project
- Forecasted return on investment when scaled nationally

**Panel interview:** Strong written applications may be invited to a panel interview before final decisions.

(Specific numerical weightings per criterion were set out in the prospectus's Annex A, which is not reproduced here.)

---

## Eligible and Ineligible Uses

**Fund supports:**
- Agile, user-centred project delivery in local government digital services
- Products and learnings that are open and reusable across the sector
- Collaborative, multi-council delivery teams

**Does not fund:**
- Single-council projects without the required partner councils
- Work that duplicates existing Local Digital Fund outputs without a clear reuse/extension rationale
- Ongoing business-as-usual IT costs unrelated to transformation

---

## Partnership & Reuse Obligations

- Lead council is accountable for grant funds
- Partner councils are expected to contribute to design, governance, and learning
- Outputs (code, research, patterns) are expected to be **published openly** so other councils can reuse them
- Successful projects are expected to share progress with the Local Digital community via Sprint Notes / blog updates

---

## Contact

**Local Digital team**, MHCLG Digital
Website: https://www.localdigital.gov.uk/
Round 6 landing page: https://www.localdigital.gov.uk/fund/local-digital-fund-round-6/

---

## Why this prospectus is in `refs/`

This shape differs meaningfully from EHCF and Pride in Place:

- **Applicant type:** local authorities (not VCFS)
- **Mandatory partnership structure** (3+ councils)
- **Phase-based funding** (Discovery / Alpha / Beta) with different award ceilings per phase
- **Panel interview stage** between written assessment and decision
- **Open-source / reuse obligations** baked into the grant
- **Signatory prerequisite** (Local Digital Declaration) — a categorical eligibility gate beyond org type

Useful as a test case for the grant-config JSON: different applicant entities, phase-dependent caps, partnership constraints, and post-award publication obligations.
