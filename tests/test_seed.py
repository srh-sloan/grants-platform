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
        "text", "textarea", "radio", "checkbox", "select",
        "number", "currency", "date", "file",
    }
    schema = json.loads((FORMS_DIR / "ehcf-application-v1.json").read_text())
    used = {field["type"] for page in schema["pages"] for field in page["fields"]}
    assert used <= supported, f"Unsupported field types: {used - supported}"
