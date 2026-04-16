"""Seed realistic demo applications for EHCF so assessors can see the dashboard.

Run with:

    python seed_demo_applications.py

Requires the DB to already be seeded (python seed.py). Creates three demo
organisations and submitted applications with different quality levels so the
assessor queue shows a range of scores and recommendations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    Grant,
    Organisation,
    User,
    UserRole,
)

_APPLICATIONS = [
    {
        "org": {
            "name": "Shelter Street CIO",
            "contact_email": "info@shelterstreet.org.uk",
        },
        "user_email": "apply@shelterstreet.org.uk",
        "answers": {
            "organisation": {
                "name": "Shelter Street CIO",
                "org_type": "CIO",
                "registration_number": "CE012345",
                "annual_income": 480000,
                "years_serving_homeless": 7,
                "operates_in_england": "yes",
            },
            "proposal": {
                "project_name": "Community Navigation and Recovery Programme",
                "fund_objective": "community_support",
                "local_challenge": (
                    "Lancaster City has seen rough sleeping counts rise from 12 in 2022 to 31 in 2024 "
                    "(MHCLG annual count). CHAIN data shows 68% of rough sleepers in our area have a "
                    "mental health need and 54% have a substance misuse history. Local authority data "
                    "identifies that 40% of those placed in temporary accommodation return to rough "
                    "sleeping within 6 months due to lack of community support. Our waitlist for "
                    "supported tenancy has averaged 14 weeks over the past year."
                ),
                "project_summary": (
                    "We will embed two trained community navigators within GP surgeries and the "
                    "local food bank to identify people at risk of rough sleeping before crisis point. "
                    "Each navigator will carry a caseload of 25 individuals, providing intensive "
                    "12-week support packages including benefits advice, mental health triage, and "
                    "move-on planning. The project directly addresses EHCF objective 1: "
                    "community-based prevention and recovery support."
                ),
            },
            "funding": {
                "funding_type": "revenue",
                "revenue_amount": 148000,
                "capital_amount": 0,
            },
            "deliverability": {
                "milestones": (
                    "Month 1-2: recruit and train navigators, establish GP and food bank partnerships. "
                    "Month 3: begin caseload intake (target 10 clients). "
                    "Month 6: first cohort completing 12-week programme (target 20 completions). "
                    "Month 12: 60 individuals supported, interim outcomes report to board. "
                    "Month 24: 130 individuals supported, external evaluation begins. "
                    "Month 36: 200 individuals supported, full evaluation submitted to MHCLG. "
                    "Governance: delivery board meets quarterly; CEO holds budget sign-off; "
                    "safeguarding lead reviews all cases monthly."
                ),
                "risks": (
                    "Risk 1: Navigator recruitment. Mitigation: salary benchmarked at 90th percentile "
                    "for sector; HR lead already in post. "
                    "Risk 2: GP partnership reluctance. Mitigation: MOU signed with two GP practices; "
                    "third in negotiation. "
                    "Risk 3: Client safeguarding incidents. Mitigation: all navigators hold DBS; "
                    "safeguarding policy reviewed annually by trustee board; clear escalation pathway "
                    "to local authority MARAC."
                ),
            },
            "declaration": {
                "contact_name": "Dr Amara Osei",
                "contact_email": "apply@shelterstreet.org.uk",
                "agree_terms": True,
            },
        },
    },
    {
        "org": {
            "name": "Fylde Coast Outreach",
            "contact_email": "grants@fyldeoutreach.org.uk",
        },
        "user_email": "apply@fyldeoutreach.org.uk",
        "answers": {
            "organisation": {
                "name": "Fylde Coast Outreach",
                "org_type": "charity",
                "registration_number": "1198734",
                "annual_income": 920000,
                "years_serving_homeless": 11,
                "operates_in_england": "yes",
            },
            "proposal": {
                "project_name": "Night Shelter Enhancement and Day Centre Expansion",
                "fund_objective": "day_services",
                "local_challenge": (
                    "Blackpool has one of the highest rough sleeping rates per capita in England. "
                    "The 2024 street count recorded 47 rough sleepers on a single night. Fylde Coast "
                    "Outreach's own service data shows demand for our day centre has increased 38% "
                    "since 2022. We have had to turn away 23 people per week on average due to "
                    "capacity. The local authority homelessness strategy (2024-2027) identifies "
                    "enhanced day services as a priority."
                ),
                "project_summary": (
                    "We will extend our day centre opening hours from 4 to 7 days per week, add a "
                    "dedicated women-only space following consultation with lived experience advisors, "
                    "and introduce on-site welfare benefits surgery twice weekly (partnering with "
                    "Citizens Advice Blackpool). This directly aligns to EHCF objective 2: day "
                    "services enhancement."
                ),
            },
            "funding": {
                "funding_type": "revenue",
                "revenue_amount": 195000,
                "capital_amount": 50000,
                "capital_year": "year_1",
            },
            "deliverability": {
                "milestones": (
                    "Month 1: procure equipment for women's space. Month 2: recruit 1.5 FTE support "
                    "workers. Month 3: 7-day operation begins. Month 6: welfare surgery running; "
                    "first impact data published internally. Year 2-3: sustain and evaluate."
                ),
                "risks": (
                    "Staffing turnover: competitive salaries and 6-month notice for funders. "
                    "Building lease renewal due Year 2: landlord engaged, renewal expected. "
                    "Safeguarding: lone worker policy in place, all staff trained annually."
                ),
            },
            "declaration": {
                "contact_name": "Priya Nair",
                "contact_email": "grants@fyldeoutreach.org.uk",
                "agree_terms": True,
            },
        },
    },
    {
        "org": {
            "name": "Hope Rising CIC",
            "contact_email": "contact@hoperising.co.uk",
        },
        "user_email": "apply@hoperising.co.uk",
        "answers": {
            "organisation": {
                "name": "Hope Rising CIC",
                "org_type": "CIC",
                "registration_number": "14567890",
                "annual_income": 120000,
                "years_serving_homeless": 3,
                "operates_in_england": "yes",
            },
            "proposal": {
                "project_name": "Peer Support and Recovery Project",
                "fund_objective": "recovery_support",
                "local_challenge": (
                    "Homelessness is a problem in our town. We have seen more people on the streets "
                    "recently and the local council has said it is getting worse. We want to help."
                ),
                "project_summary": (
                    "We will provide peer support sessions for people who have experienced "
                    "homelessness, using volunteers with lived experience. Sessions will run weekly "
                    "at our community hub."
                ),
            },
            "funding": {
                "funding_type": "revenue",
                "revenue_amount": 75000,
                "capital_amount": 0,
            },
            "deliverability": {
                "milestones": (
                    "We will set up the project in Month 1 and start sessions in Month 2. "
                    "We hope to see 50 people over the year."
                ),
                "risks": (
                    "Volunteers might not be available. We will manage this by recruiting more."
                ),
            },
            "declaration": {
                "contact_name": "James Bell",
                "contact_email": "contact@hoperising.co.uk",
                "agree_terms": True,
            },
        },
    },
]


def seed_demo_applications() -> None:
    """Upsert demo applications for the EHCF grant."""
    grant = db.session.execute(
        select(Grant).where(Grant.slug == "ehcf")
    ).scalar_one_or_none()

    if grant is None:
        print("ERROR: ehcf grant not found. Run seed.py first.")
        return

    print("\nDemo applications:")
    print("-" * 60)

    for spec in _APPLICATIONS:
        org_name = spec["org"]["name"]

        # Check if already seeded
        existing_org = db.session.execute(
            select(Organisation).where(Organisation.name == org_name)
        ).scalar_one_or_none()

        if existing_org is not None:
            existing_app = db.session.execute(
                select(Application).where(Application.org_id == existing_org.id)
            ).scalar_one_or_none()
            if existing_app is not None:
                print(f"  {org_name}  (already exists, id={existing_app.id})")
                continue

        # Create or reuse org
        org = existing_org or Organisation(
            name=org_name,
            contact_email=spec["org"]["contact_email"],
        )
        if existing_org is None:
            db.session.add(org)

        # Create applicant user
        user_email = spec["user_email"]
        user = db.session.execute(
            select(User).where(User.email == user_email)
        ).scalar_one_or_none()
        if user is None:
            db.session.flush()
            user = User(
                email=user_email,
                password_hash=generate_password_hash("Demo1234567!"),
                role=UserRole.APPLICANT,
                org_id=org.id if existing_org else None,
            )
            if not existing_org:
                db.session.flush()
                user.org_id = org.id
            db.session.add(user)

        db.session.flush()

        # Create submitted application
        app = Application(
            org_id=org.id,
            grant_id=grant.id,
            status=ApplicationStatus.SUBMITTED,
            answers_json=spec["answers"],
            submitted_at=datetime.now(UTC),
        )
        db.session.add(app)
        db.session.flush()
        print(f"  {org_name}  (created, id={app.id})")

    db.session.commit()
    print("-" * 60)
    print("Done. Open /assess/ to see the queue.")


def main() -> None:
    app = create_app()
    with app.app_context():
        seed_demo_applications()


if __name__ == "__main__":
    main()
