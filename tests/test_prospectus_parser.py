"""Tests for the prospectus parser (spike: grant import from CSV / free text).

Unit tests cover the pure CSV parser only — no AI calls.
The admin route smoke tests use a mocked generate_grant_artifacts to avoid
hitting the Claude API in CI.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.prospectus_parser import parse_prospectus_csv


# ---------------------------------------------------------------------------
# CSV parser unit tests (pure — no I/O)
# ---------------------------------------------------------------------------

_SAMPLE_CSV = """\
type,key,value,extra1,extra2,extra3
meta,name,Test Grant,,,
meta,slug,test-grant,,,
meta,summary,A test grant,,,
meta,contact_email,test@example.gov.uk,,,
meta,total_budget,5000000,,,
meta,duration_years,3,,,
eligibility,org_type,in,charity|CIO|CIC,Must be a qualifying organisation,
eligibility,operates_in_england,equals,true,Must operate in England,
eligibility,annual_income,max,2000000,Annual income up to £2m,
eligibility,years_experience,min,2,At least 2 years experience,
criterion,strategic_alignment,Strategic alignment,25,3,true
criterion,community_impact,Community impact,25,3,true
criterion,deliverability,Deliverability,30,3,false
criterion,value_for_money,Value for money,20,3,false
"""


def test_parse_meta():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    assert data["meta"]["name"] == "Test Grant"
    assert data["meta"]["slug"] == "test-grant"
    assert data["meta"]["total_budget"] == "5000000"
    assert data["meta"]["contact_email"] == "test@example.gov.uk"


def test_parse_eligibility_in_rule():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    org_type_rule = next(r for r in data["eligibility"] if r["id"] == "org_type")
    assert org_type_rule["type"] == "in"
    assert org_type_rule["values"] == ["charity", "CIO", "CIC"]
    assert "Must be" in org_type_rule["label"]


def test_parse_eligibility_equals_boolean():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    england_rule = next(r for r in data["eligibility"] if r["id"] == "operates_in_england")
    assert england_rule["type"] == "equals"
    assert england_rule["value"] is True


def test_parse_eligibility_max_numeric():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    income_rule = next(r for r in data["eligibility"] if r["id"] == "annual_income")
    assert income_rule["type"] == "max"
    assert income_rule["value"] == 2_000_000


def test_parse_eligibility_min_numeric():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    exp_rule = next(r for r in data["eligibility"] if r["id"] == "years_experience")
    assert exp_rule["type"] == "min"
    assert exp_rule["value"] == 2


def test_parse_criteria_count():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    assert len(data["criteria"]) == 4


def test_parse_criteria_fields():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    alignment = next(c for c in data["criteria"] if c["id"] == "strategic_alignment")
    assert alignment["label"] == "Strategic alignment"
    assert alignment["weight"] == 25
    assert alignment["max"] == 3
    assert alignment["auto_reject_on_zero"] is True


def test_parse_criteria_auto_reject_false():
    data = parse_prospectus_csv(_SAMPLE_CSV)
    delivery = next(c for c in data["criteria"] if c["id"] == "deliverability")
    assert delivery["auto_reject_on_zero"] is False


def test_comment_rows_skipped():
    csv_with_comments = "type,key,value,extra1,extra2,extra3\n# this is a comment\nmeta,name,X,,,\n"
    data = parse_prospectus_csv(csv_with_comments)
    assert data["meta"].get("name") == "X"
    # comment row does not appear as a meta/eligibility/criterion entry
    assert len(data["eligibility"]) == 0


def test_empty_csv_returns_empty_structure():
    data = parse_prospectus_csv("type,key,value,extra1,extra2,extra3\n")
    assert data == {"meta": {}, "eligibility": [], "criteria": []}


# ---------------------------------------------------------------------------
# Admin route smoke tests (mocked AI)
# ---------------------------------------------------------------------------

_MOCK_RESULT = {
    "grant_config": {
        "slug": "test-grant",
        "name": "Test Grant",
        "status": "draft",
        "summary": "A test grant",
        "contact_email": "",
        "prospectus_url": "",
        "eligibility": [],
        "criteria": [],
        "award_ranges": {"revenue_min": None, "revenue_max": None, "capital_min": None, "capital_max": None, "total_budget": 0, "duration_years": 1},
        "timeline": {"opens_on": "", "closes_on": "", "assessment_window": "", "moderation_window": "", "outcome_notification": "", "first_payments": ""},
        "forms": {"application": "test-grant-application-v1", "assessment": "test-grant-assessment-v1"},
    },
    "application_schema": {
        "id": "test-grant-application",
        "version": 1,
        "kind": "application",
        "pages": [],
    },
    "assessment_schema": {
        "id": "test-grant-assessment",
        "version": 1,
        "kind": "assessment",
        "description": "Generated",
        "scoring": {"source": "grant.config_json.criteria", "score_field": "score", "notes_field": "notes", "score_min": 0, "score_max": 3, "notes_required": True},
    },
    "errors": [],
}


@pytest.fixture()
def admin_client(app, db):
    """Flask test client logged in as an admin user."""
    from app.models import User, UserRole
    from werkzeug.security import generate_password_hash

    admin = User(
        email="admin@test.local",
        password_hash=generate_password_hash("password"),
        role=UserRole.ADMIN,
    )
    db.session.add(admin)
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
    return client


def test_admin_index_accessible(admin_client):
    resp = admin_client.get("/admin/")
    assert resp.status_code == 200
    assert b"Grant administration" in resp.data


def test_admin_import_get(admin_client):
    resp = admin_client.get("/admin/grants/import")
    assert resp.status_code == 200
    assert b"Import grant from prospectus" in resp.data


def test_admin_download_template(admin_client):
    resp = admin_client.get("/admin/grants/template.csv")
    assert resp.status_code == 200
    assert b"type,key,value" in resp.data
    assert resp.content_type.startswith("text/csv")


def test_admin_import_post_csv(admin_client):
    from io import BytesIO

    csv_bytes = b"type,key,value,extra1,extra2,extra3\nmeta,name,X,,,\n"
    with patch("app.admin.generate_grant_artifacts", return_value=_MOCK_RESULT):
        resp = admin_client.post(
            "/admin/grants/import",
            data={"prospectus_file": (BytesIO(csv_bytes), "test.csv")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    assert b"Review generated grant configuration" in resp.data


def test_admin_import_post_no_input(admin_client):
    resp = admin_client.post(
        "/admin/grants/import",
        data={},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert b"Upload a CSV file or paste prospectus text" in resp.data


def test_admin_save_grant(admin_client, db):
    from app.models import Grant

    resp = admin_client.post(
        "/admin/grants/save",
        data={
            "grant_config_json": json.dumps(_MOCK_RESULT["grant_config"]),
            "application_schema_json": json.dumps(_MOCK_RESULT["application_schema"]),
            "assessment_schema_json": json.dumps(_MOCK_RESULT["assessment_schema"]),
        },
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 302  # redirect to admin.index
    assert Grant.query.filter_by(slug="test-grant").count() == 1


def _make_draft_grant(db, slug="draft-grant", with_forms=True, weight_total=100):
    """Helper: create a draft grant with valid criteria and optionally an application form."""
    from app.models import Form, FormKind, Grant, GrantStatus

    criteria = [{"id": "quality", "label": "Quality", "weight": weight_total, "max": 3, "auto_reject_on_zero": False}]
    grant = Grant(
        slug=slug,
        name="Draft Grant",
        status=GrantStatus.DRAFT,
        config_json={
            "slug": slug,
            "criteria": criteria,
            "eligibility": [{"id": "org_type", "type": "in", "label": "Org type", "values": ["charity"]}],
        },
    )
    db.session.add(grant)
    db.session.flush()
    if with_forms:
        db.session.add(Form(grant_id=grant.id, kind=FormKind.APPLICATION, version=1, schema_json={"pages": []}))
    db.session.commit()
    return grant


def test_grant_detail_page(admin_client, db):
    grant = _make_draft_grant(db)
    resp = admin_client.get(f"/admin/grants/{grant.id}")
    assert resp.status_code == 200
    assert b"Draft Grant" in resp.data
    assert b"Publish grant" in resp.data


def test_publish_valid_grant(admin_client, db):
    from app.models import Grant, GrantStatus

    grant = _make_draft_grant(db)
    resp = admin_client.post(f"/admin/grants/{grant.id}/publish")
    assert resp.status_code == 302
    db.session.refresh(grant)
    assert grant.status == GrantStatus.OPEN


def test_publish_blocked_bad_weights(admin_client, db):
    from app.models import GrantStatus

    grant = _make_draft_grant(db, slug="bad-weights", weight_total=50)
    resp = admin_client.post(f"/admin/grants/{grant.id}/publish")
    assert resp.status_code == 302
    db.session.refresh(grant)
    assert grant.status == GrantStatus.DRAFT  # unchanged


def test_publish_blocked_no_form(admin_client, db):
    from app.models import GrantStatus

    grant = _make_draft_grant(db, slug="no-form", with_forms=False)
    resp = admin_client.post(f"/admin/grants/{grant.id}/publish")
    assert resp.status_code == 302
    db.session.refresh(grant)
    assert grant.status == GrantStatus.DRAFT  # unchanged


def test_close_open_grant(admin_client, db):
    from app.models import Grant, GrantStatus

    grant = _make_draft_grant(db, slug="open-grant")
    grant.status = GrantStatus.OPEN
    db.session.commit()

    resp = admin_client.post(f"/admin/grants/{grant.id}/close")
    assert resp.status_code == 302
    db.session.refresh(grant)
    assert grant.status == GrantStatus.CLOSED


def test_publish_already_open_is_noop(admin_client, db):
    from app.models import Grant, GrantStatus

    grant = _make_draft_grant(db, slug="already-open")
    grant.status = GrantStatus.OPEN
    db.session.commit()

    resp = admin_client.post(f"/admin/grants/{grant.id}/publish")
    assert resp.status_code == 302
    db.session.refresh(grant)
    assert grant.status == GrantStatus.OPEN  # unchanged, error flashed


def test_admin_forbidden_for_applicant(app, db):
    from app.models import User, UserRole
    from werkzeug.security import generate_password_hash

    applicant = User(
        email="applicant@test.local",
        password_hash=generate_password_hash("password"),
        role=UserRole.APPLICANT,
    )
    db.session.add(applicant)
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(applicant.id)

    resp = client.get("/admin/")
    assert resp.status_code == 403


