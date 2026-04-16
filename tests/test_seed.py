"""Tests for the seed loader and the pinned grant-config contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Form, FormKind, Grant
from seed import FORMS_DIR, GRANTS_DIR, seed_into_session, validate_grant_config


def test_ehcf_grant_config_contract():
    """The on-disk EHCF grant config must satisfy the cross-stream contract."""
    config = json.loads((GRANTS_DIR / "ehcf.json").read_text())
    validate_grant_config(config, GRANTS_DIR / "ehcf.json")


def test_validator_rejects_bad_weights(tmp_path: Path):
    bad = {
        "slug": "x",
        "name": "X",
        "status": "open",
        "criteria": [
            {"id": "a", "label": "A", "weight": 40, "max": 3},
            {"id": "b", "label": "B", "weight": 40, "max": 3},
        ],
    }
    with pytest.raises(ValueError, match="sum to 100"):
        validate_grant_config(bad, tmp_path / "x.json")


def test_validator_rejects_missing_criterion_keys(tmp_path: Path):
    bad = {
        "slug": "x",
        "name": "X",
        "status": "open",
        "criteria": [{"id": "a", "weight": 100}],  # missing label + max
    }
    with pytest.raises(ValueError, match="missing keys"):
        validate_grant_config(bad, tmp_path / "x.json")


def test_seed_loads_ehcf(app, db):
    """seed_into_session populates the grant + its form from disk."""
    seed_into_session(reset=False)

    grant = db.session.execute(select(Grant).where(Grant.slug == "ehcf")).scalar_one()
    assert grant.name.startswith("Ending Homelessness")
    assert len(grant.config_json["criteria"]) == 7

    application_form = db.session.execute(
        select(Form).where(Form.grant_id == grant.id, Form.kind == FormKind.APPLICATION)
    ).scalar_one()
    assert application_form.schema_json["id"] == "ehcf-application"
    assert application_form.schema_json["pages"]


def test_ehcf_application_form_uses_supported_field_types():
    """All field types in the seeded form must be in the agreed set (CLAUDE.md §6)."""
    supported = {
        "text",
        "textarea",
        "radio",
        "checkbox",
        "select",
        "number",
        "currency",
        "date",
        "file",
    }
    schema = json.loads((FORMS_DIR / "ehcf-application-v1.json").read_text())
    used = {field["type"] for page in schema["pages"] for field in page["fields"]}
    assert used <= supported, f"Unsupported field types: {used - supported}"


# --- Common Ground Award tests ---


def test_common_ground_grant_config_contract():
    """The on-disk Common Ground grant config must satisfy the cross-stream contract."""
    config = json.loads((GRANTS_DIR / "common-ground.json").read_text())
    validate_grant_config(config, GRANTS_DIR / "common-ground.json")


def test_common_ground_has_five_criteria():
    """Common Ground must have exactly 5 criteria with non-uniform weights summing to 100."""
    config = json.loads((GRANTS_DIR / "common-ground.json").read_text())
    criteria = config["criteria"]
    assert len(criteria) == 5
    weights = [c["weight"] for c in criteria]
    assert sum(weights) == 100
    # Non-uniform: not all weights are the same
    assert len(set(weights)) > 1


def test_common_ground_is_capital_only():
    """Common Ground is a capital-only scheme — award_ranges should not include revenue."""
    config = json.loads((GRANTS_DIR / "common-ground.json").read_text())
    award = config["award_ranges"]
    assert "capital_max" in award
    assert "revenue_min" not in award
    assert "revenue_max" not in award


def test_common_ground_application_form_uses_supported_field_types():
    """All field types in the Common Ground form must be in the agreed set."""
    supported = {
        "text",
        "textarea",
        "radio",
        "checkbox",
        "select",
        "number",
        "currency",
        "date",
        "file",
    }
    schema = json.loads((FORMS_DIR / "common-ground-application-v1.json").read_text())
    used = {field["type"] for page in schema["pages"] for field in page["fields"]}
    assert used <= supported, f"Unsupported field types: {used - supported}"


def test_common_ground_application_form_has_pages():
    """Common Ground application form must have at least one page with fields."""
    schema = json.loads((FORMS_DIR / "common-ground-application-v1.json").read_text())
    assert schema["kind"] == "application"
    assert len(schema["pages"]) >= 3
    for page in schema["pages"]:
        assert page["id"]
        assert page["title"]
        assert len(page["fields"]) >= 1


def test_seed_loads_common_ground(app, db):
    """seed_into_session populates the Common Ground grant + its form from disk."""
    seed_into_session(reset=False)

    grant = db.session.execute(select(Grant).where(Grant.slug == "common-ground")).scalar_one()
    assert grant.name == "Common Ground Award"
    assert len(grant.config_json["criteria"]) == 5

    application_form = db.session.execute(
        select(Form).where(Form.grant_id == grant.id, Form.kind == FormKind.APPLICATION)
    ).scalar_one()
    assert application_form.schema_json["id"] == "common-ground-application"
    assert application_form.schema_json["pages"]


def test_seed_loads_both_grants(app, db):
    """Both EHCF and Common Ground must load in a single seed run."""
    seed_into_session(reset=False)

    grants = db.session.execute(select(Grant)).scalars().all()
    slugs = {g.slug for g in grants}
    assert "ehcf" in slugs
    assert "common-ground" in slugs
