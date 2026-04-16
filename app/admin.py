"""Admin blueprint — grant management and prospectus-driven grant onboarding.

Routes
------
GET  /admin/                      admin landing (list of grants)
GET  /admin/grants/<id>           grant detail + publish/close controls
POST /admin/grants/<id>/publish   publish a draft grant (draft → open)
POST /admin/grants/<id>/close     close a live grant (open → closed)
GET  /admin/grants/import         upload prospectus form
POST /admin/grants/import         process upload, run AI extraction, show preview
GET  /admin/grants/template.csv   download the CSV prospectus template
POST /admin/grants/save           save a reviewed grant config + form schemas to DB

All routes require the ADMIN role.
"""

from __future__ import annotations

import json
from functools import wraps

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Form, FormKind, Grant, GrantStatus, UserRole
from app.prospectus_parser import generate_grant_artifacts, parse_prospectus_csv

# Transitions allowed per current status.
_PUBLISH_FROM = {GrantStatus.DRAFT}
_CLOSE_FROM = {GrantStatus.OPEN}

bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------


def admin_required(view):
    """Restrict a route to ADMIN role users only."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ADMIN:
            abort(403)
        return view(*args, **kwargs)

    return login_required(wrapped)


# ---------------------------------------------------------------------------
# CSV template (constant — served as a file download)
# ---------------------------------------------------------------------------

_CSV_TEMPLATE = """\
type,key,value,extra1,extra2,extra3
# --- Grant metadata rows ---
# meta rows: key = field name, value = field value
meta,name,My Grant Name,,,
meta,slug,my-grant,,,
meta,summary,A brief description of the grant fund.,,,
meta,contact_email,grant@example.gov.uk,,,
meta,total_budget,5000000,,,
meta,duration_years,3,,,
meta,revenue_min,10000,,,
meta,revenue_max,100000,,,
meta,capital_min,,,,
meta,capital_max,,,,
meta,opens_on,2026-06-01,,,
meta,closes_on,2026-09-01,,,
# --- Eligibility rules ---
# eligibility rows: key = rule_id, value = rule_type (in|equals|max|min)
# extra1 = the threshold or pipe-separated allowed values
# extra2 = human-readable label
eligibility,org_type,in,charity|CIO|CIC|CBS,Organisation type must be one of the listed types,
eligibility,operates_in_england,equals,true,Organisation must operate in England,
eligibility,annual_income,max,2000000,Annual income no greater than £2m,
eligibility,years_experience,min,2,At least 2 years delivering relevant services,
# --- Scoring criteria ---
# criterion rows: key = criterion_id, value = criterion label
# extra1 = weight (integer; all weights must sum to 100)
# extra2 = max score (usually 3)
# extra3 = auto_reject_on_zero (true|false)
criterion,strategic_alignment,Strategic alignment,25,3,true
criterion,community_impact,Community impact,25,3,true
criterion,deliverability,Deliverability,25,3,false
criterion,sustainability,Sustainability,15,3,false
criterion,value_for_money,Value for money,10,3,false
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/")
@admin_required
def index():
    grants = Grant.query.order_by(Grant.name).all()
    return render_template("admin/index.html", grants=grants)


@bp.route("/grants/<int:grant_id>")
@admin_required
def grant_detail(grant_id: int):
    grant = db.get_or_404(Grant, grant_id)
    criteria = grant.config_json.get("criteria", [])
    eligibility = grant.config_json.get("eligibility", [])
    award_ranges = grant.config_json.get("award_ranges", {})
    timeline = grant.config_json.get("timeline", {})
    weight_total = sum(c.get("weight", 0) for c in criteria)
    forms = Form.query.filter_by(grant_id=grant.id).order_by(Form.kind).all()
    return render_template(
        "admin/grant_detail.html",
        grant=grant,
        criteria=criteria,
        eligibility=eligibility,
        award_ranges=award_ranges,
        timeline=timeline,
        weight_total=weight_total,
        forms=forms,
        can_publish=grant.status in _PUBLISH_FROM,
        can_close=grant.status in _CLOSE_FROM,
    )


@bp.post("/grants/<int:grant_id>/publish")
@admin_required
def publish_grant(grant_id: int):
    grant = db.get_or_404(Grant, grant_id)
    if grant.status not in _PUBLISH_FROM:
        flash(f"'{grant.name}' cannot be published from status '{grant.status.value}'.", "error")
        return redirect(url_for("admin.grant_detail", grant_id=grant_id))

    # Validate minimum requirements before going live.
    criteria = grant.config_json.get("criteria", [])
    eligibility = grant.config_json.get("eligibility", [])
    app_form = Form.query.filter_by(grant_id=grant.id, kind=FormKind.APPLICATION).first()

    errors = []
    if not criteria:
        errors.append("Grant has no scoring criteria — add at least one before publishing.")
    elif sum(c.get("weight", 0) for c in criteria) != 100:
        errors.append("Criterion weights do not sum to 100 — fix the grant config before publishing.")
    if not eligibility:
        errors.append("Grant has no eligibility rules defined.")
    if app_form is None:
        errors.append("No application form found — the grant cannot be applied for without one.")

    if errors:
        for msg in errors:
            flash(msg, "error")
        return redirect(url_for("admin.grant_detail", grant_id=grant_id))

    grant.status = GrantStatus.OPEN
    db.session.commit()
    flash(f"'{grant.name}' is now live and open for applications.", "success")
    return redirect(url_for("admin.grant_detail", grant_id=grant_id))


@bp.post("/grants/<int:grant_id>/close")
@admin_required
def close_grant(grant_id: int):
    grant = db.get_or_404(Grant, grant_id)
    if grant.status not in _CLOSE_FROM:
        flash(f"'{grant.name}' is not currently open.", "error")
        return redirect(url_for("admin.grant_detail", grant_id=grant_id))

    grant.status = GrantStatus.CLOSED
    db.session.commit()
    flash(f"'{grant.name}' has been closed. No new applications will be accepted.", "success")
    return redirect(url_for("admin.grant_detail", grant_id=grant_id))


@bp.route("/grants/template.csv")
@admin_required
def download_template():
    """Serve the CSV prospectus template as a download."""
    return Response(
        _CSV_TEMPLATE,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=prospectus-template.csv"},
    )


@bp.route("/grants/import", methods=["GET", "POST"])
@admin_required
def import_grant():
    if request.method == "GET":
        return render_template("admin/grant_import.html")

    file = request.files.get("prospectus_file")
    raw_text = (request.form.get("prospectus_text") or "").strip()

    if (not file or not file.filename) and not raw_text:
        flash("Upload a CSV file or paste prospectus text.", "error")
        return render_template("admin/grant_import.html")

    content = ""
    is_csv = False

    if file and file.filename:
        content = file.read().decode("utf-8", errors="replace")
        is_csv = file.filename.lower().endswith(".csv")
    else:
        content = raw_text

    structured = None
    if is_csv:
        try:
            structured = parse_prospectus_csv(content)
        except Exception as exc:
            flash(f"CSV parse error: {exc}", "error")
            return render_template("admin/grant_import.html")

    try:
        result = generate_grant_artifacts(structured, content)
    except RuntimeError as exc:
        # ANTHROPIC_API_KEY not set — give a clear message
        flash(str(exc), "error")
        return render_template("admin/grant_import.html")

    return render_template(
        "admin/grant_preview.html",
        grant_config_json=json.dumps(result["grant_config"], indent=2),
        application_schema_json=json.dumps(result["application_schema"], indent=2),
        assessment_schema_json=json.dumps(result["assessment_schema"], indent=2),
        errors=result["errors"],
    )


@bp.route("/grants/save", methods=["POST"])
@admin_required
def save_grant():
    """Save a reviewed (and optionally edited) grant config to the database."""
    try:
        grant_config = json.loads(request.form["grant_config_json"])
        application_schema = json.loads(request.form["application_schema_json"])
        assessment_schema = json.loads(request.form["assessment_schema_json"])
    except (KeyError, json.JSONDecodeError) as exc:
        flash(f"Invalid JSON — could not save: {exc}", "error")
        return redirect(url_for("admin.import_grant"))

    slug = (grant_config.get("slug") or "").strip()
    if not slug:
        flash("Grant config must have a non-empty slug.", "error")
        return redirect(url_for("admin.import_grant"))

    grant = Grant(
        slug=slug,
        name=grant_config.get("name") or slug,
        status=GrantStatus.DRAFT,
        config_json=grant_config,
    )
    db.session.add(grant)

    try:
        db.session.flush()  # get grant.id before adding forms
    except IntegrityError:
        db.session.rollback()
        flash(f"A grant with slug '{slug}' already exists. Edit the slug and try again.", "error")
        return render_template(
            "admin/grant_preview.html",
            grant_config_json=request.form["grant_config_json"],
            application_schema_json=request.form["application_schema_json"],
            assessment_schema_json=request.form["assessment_schema_json"],
            errors=[],
        )

    app_form = Form(
        grant_id=grant.id,
        kind=FormKind.APPLICATION,
        version=1,
        schema_json=application_schema,
    )
    assess_form = Form(
        grant_id=grant.id,
        kind=FormKind.ASSESSMENT,
        version=1,
        schema_json=assessment_schema,
    )
    db.session.add_all([app_form, assess_form])
    db.session.commit()

    flash(f"Grant '{grant.name}' saved as draft (slug: {slug}).", "success")
    return redirect(url_for("admin.index"))
