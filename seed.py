"""Seed the database with grants + forms loaded from disk.

Run with:

    python seed.py            # idempotent upsert of grants and forms
    python seed.py --reset    # drop and recreate the schema, then seed

Grant configs live in ``seed/grants/<slug>.json``. Form schemas live in
``app/forms/<form-id>.json`` and are referenced from the grant config's
``forms`` map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Form, FormKind, Grant, GrantStatus, Organisation, User, UserRole

GRANTS_DIR = Path(__file__).resolve().parent / "seed" / "grants"
FORMS_DIR = Path(__file__).resolve().parent / "app" / "forms"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_grant_config(config: dict, path: Path) -> None:
    """Fail loudly if a grant config breaks the pinned contract."""
    required = {"slug", "name", "status", "criteria"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")

    criterion_keys = {"id", "label", "weight", "max"}
    for criterion in config["criteria"]:
        gaps = criterion_keys - criterion.keys()
        if gaps:
            raise ValueError(
                f"{path}: criterion {criterion.get('id')!r} missing keys {sorted(gaps)}"
            )

    weights = sum(c["weight"] for c in config["criteria"])
    if weights != 100:
        raise ValueError(
            f"{path}: criterion weights must sum to 100 (got {weights})"
        )

    ids = [c["id"] for c in config["criteria"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate criterion ids in {ids}")


def upsert_grant(config: dict) -> Grant:
    grant = db.session.execute(
        select(Grant).where(Grant.slug == config["slug"])
    ).scalar_one_or_none()

    if grant is None:
        grant = Grant(slug=config["slug"])
        db.session.add(grant)

    grant.name = config["name"]
    grant.status = GrantStatus(config["status"])
    grant.config_json = config
    return grant


def upsert_form(grant: Grant, form_id: str) -> Form:
    path = FORMS_DIR / f"{form_id}.json"
    schema = load_json(path)
    kind = FormKind(schema["kind"])
    version = int(schema.get("version", 1))

    form = db.session.execute(
        select(Form).where(
            Form.grant_id == grant.id, Form.kind == kind, Form.version == version
        )
    ).scalar_one_or_none()

    if form is None:
        form = Form(grant=grant, kind=kind, version=version)
        db.session.add(form)

    form.schema_json = schema
    return form


# Demo credentials printed to stdout on seed so they are easy to find.
_DEMO_USERS = [
    {
        "email": "assessor@ehcf.test",
        "password": "Assessor123!",
        "role": UserRole.ASSESSOR,
        "org_name": None,
    },
    {
        "email": "admin@ehcf.test",
        "password": "Admin1234567!",
        "role": UserRole.ADMIN,
        "org_name": None,
    },
    {
        "email": "applicant@ehcf.test",
        "password": "Applicant123!",
        "role": UserRole.APPLICANT,
        "org_name": "Demo Organisation",
    },
    {
        "email": "William.May@communities.gov.uk",
        "password": "ABCDE12345",
        "role": UserRole.APPLICANT,
        "org_name": "William May Organisation",
    },
]


def seed_demo_users() -> None:
    """Upsert demo users for local development and judging demos.

    Credentials are printed to stdout. These accounts must never be used in
    production -- they exist solely to make the demo runnable without manual
    DB manipulation.
    """
    print("\nDemo user accounts:")
    print("-" * 50)

    for spec in _DEMO_USERS:
        existing = db.session.execute(
            select(User).where(User.email == spec["email"])
        ).scalar_one_or_none()

        if existing is not None:
            print(f"  {spec['role'].value:<12} {spec['email']}  (already exists)")
            continue

        org_id = None
        if spec["org_name"]:
            org = Organisation(
                name=spec["org_name"],
                contact_email=spec["email"],
            )
            db.session.add(org)
            db.session.flush()
            org_id = org.id

        user = User(
            email=spec["email"],
            password_hash=generate_password_hash(spec["password"]),
            role=spec["role"],
            org_id=org_id,
        )
        db.session.add(user)
        print(f"  {spec['role'].value:<12} {spec['email']}  password: {spec['password']}")

    print("-" * 50)


def seed_into_session(reset: bool = False) -> None:
    """Populate the current session's DB. Requires an active app context."""
    if reset:
        db.drop_all()
    db.create_all()

    grant_paths = sorted(GRANTS_DIR.glob("*.json"))
    if not grant_paths:
        print(f"No grant configs found in {GRANTS_DIR}", file=sys.stderr)
        return

    for path in grant_paths:
        config = load_json(path)
        validate_grant_config(config, path)
        grant = upsert_grant(config)
        db.session.flush()  # ensure grant.id for form FK
        for form_id in (config.get("forms") or {}).values():
            upsert_form(grant, form_id)
        print(f"Seeded grant: {config['slug']} ({config['name']})")

    seed_demo_users()
    db.session.commit()


def seed(reset: bool = False) -> None:
    """CLI entry: create the app, then seed within its context."""
    app = create_app()
    with app.app_context():
        seed_into_session(reset=reset)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed grants + forms into the DB.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables before seeding (destructive).",
    )
    args = parser.parse_args()
    seed(reset=args.reset)


if __name__ == "__main__":
    main()
