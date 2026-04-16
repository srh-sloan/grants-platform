"""Assessor routes: queue, application detail, scoring, decision, allocation, user management, monitoring.

**Stream ownership:** Assessor & scoring (Stream C).

URL prefix: ``/assess``.

Routes
------
GET  /assess/                     -- application queue (filterable)
GET  /assess/<app_id>             -- detail: answers + AI assessment + scoring form
POST /assess/<app_id>/score       -- save manual scores
POST /assess/<app_id>/flag        -- flag for moderation review
POST /assess/<app_id>/decision    -- record final decision + notify applicant
GET  /assess/<app_id>/monitoring  -- monitoring plan view
POST /assess/<app_id>/monitoring  -- generate monitoring plan via AI
GET  /assess/allocation           -- ranked allocation dashboard
GET  /assess/users                -- list assessor/admin users (admin only)
GET  /assess/users/new            -- form to create a new assessor account (admin only)
POST /assess/users/new            -- create the assessor account
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import textwrap
from datetime import UTC, datetime
from email.mime.text import MIMEText

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from wtforms import PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import EqualTo, InputRequired, Length, Regexp, ValidationError

from app.auth import assessor_required
from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    Assessment,
    AssessmentRecommendation,
    Organisation,
    User,
    UserRole,
)
from app.scoring import (
    all_criteria_scored,
    calculate_weighted_score,
    decision_allowed,
    declaration_gate_status,
    eligibility_gate_status,
    has_auto_reject,
    max_weighted_total,
)

log = logging.getLogger(__name__)

bp = Blueprint("assessor", __name__, url_prefix="/assess")

_EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_EMAIL_MESSAGE = "Enter an email address in the correct format, like name@example.com"
_PASSWORD_MIN_LENGTH = 10


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


class _CsrfForm(FlaskForm):
    """No fields -- used only for the hidden CSRF token on POST buttons."""


class CreateAssessorForm(FlaskForm):
    """Form for an admin to create a new assessor or admin account."""

    email = StringField(
        "Email address",
        validators=[
            InputRequired(message="Enter an email address"),
            Length(max=255),
            Regexp(_EMAIL_REGEX, message=_EMAIL_MESSAGE),
        ],
    )
    role = SelectField(
        "Role",
        choices=[
            (UserRole.ASSESSOR.value, "Assessor"),
            (UserRole.ADMIN.value, "Admin"),
        ],
        validators=[InputRequired()],
    )
    password = PasswordField(
        "Password",
        validators=[
            InputRequired(message="Enter a password"),
            Length(min=_PASSWORD_MIN_LENGTH, max=128,
                   message=f"Password must be at least {_PASSWORD_MIN_LENGTH} characters"),
        ],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            InputRequired(message="Confirm the password"),
            EqualTo("password", message="Passwords must match"),
        ],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field: StringField) -> None:
        email = (field.data or "").strip().lower()
        if not email:
            return
        existing = db.session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationError("An account with this email already exists")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _admin_required():
    """Abort with 403 if the current user is not an admin."""
    if not current_user.is_admin:
        abort(403)


# ---------------------------------------------------------------------------
# Application helpers
# ---------------------------------------------------------------------------


def _get_application_or_404(app_id: int) -> Application:
    application = db.session.get(Application, app_id)
    if application is None or application.status == ApplicationStatus.DRAFT:
        abort(404)
    return application


def _get_or_create_assessment(application: Application) -> Assessment:
    assessment = Assessment.query.filter_by(application_id=application.id).first()
    if assessment is None:
        from app.assessor_ai import _get_or_create_ai_user
        ai_user = _get_or_create_ai_user()
        assessment = Assessment(
            application_id=application.id,
            assessor_id=ai_user.id,
            scores_json={},
            notes_json={},
        )
        db.session.add(assessment)
        db.session.flush()
    return assessment


def _notify_applicant(
    application: Application,
    recommendation: AssessmentRecommendation,
    decision_notes: str,
) -> None:
    """Email the applicant's contact address with their outcome. Fails silently."""
    org = application.organisation
    if org is None or not org.contact_email:
        log.warning("notify_applicant: no contact email for application %s", application.id)
        return

    recipient = org.contact_email
    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", "grants-platform@noreply.local")

    rec_label = {
        AssessmentRecommendation.FUND: "SUCCESSFUL",
        AssessmentRecommendation.REJECT: "UNSUCCESSFUL",
        AssessmentRecommendation.REFER: "REFERRED FOR FURTHER REVIEW",
    }.get(recommendation, recommendation.value.upper())

    body = textwrap.dedent("""
        Dear {org_name},

        Thank you for your application to the {grant_name}.

        We have now reviewed your application and our decision is:

            {rec_label}

        {notes_section}

        If you have any questions about this decision, please contact us at
        {contact_email}.

        Yours sincerely,
        The {grant_name} Assessment Team
    """).strip().format(
        org_name=org.name,
        grant_name=application.grant.name,
        rec_label=rec_label,
        notes_section=(
            "Additional information from the assessment panel:\n\n    " + decision_notes
            if decision_notes else ""
        ),
        contact_email=application.grant.config_json.get(
            "contact_email", "grants@communities.gov.uk"
        ),
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "[{}] Your {} application outcome".format(
        rec_label, application.grant.name
    )
    msg["From"] = smtp_from
    msg["To"] = recipient

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [recipient], msg.as_string())
        server.quit()
        log.info("Outcome notification sent to %s", recipient)
    except Exception as exc:
        log.warning("Failed to send outcome notification: %s", exc)


# ---------------------------------------------------------------------------
# Application queue + detail
# ---------------------------------------------------------------------------


@bp.get("/")
@assessor_required
def queue():
    status_filter = request.args.get("status", "")
    rec_filter = request.args.get("recommendation", "")

    stmt = (
        select(Application, Assessment)
        .outerjoin(Assessment, Assessment.application_id == Application.id)
        .where(Application.status != ApplicationStatus.DRAFT)
        .order_by(Application.submitted_at.desc())
    )
    rows = db.session.execute(stmt).all()

    if status_filter:
        rows = [(a, s) for a, s in rows if a.status.value == status_filter]
    if rec_filter:
        rows = [
            (a, s) for a, s in rows
            if s and s.recommendation and s.recommendation.value == rec_filter
        ]

    grant_max_totals: dict[int, int] = {}
    grant_criteria_ids: dict[int, list[str]] = {}
    for app_obj, _ in rows:
        gid = app_obj.grant_id
        if gid not in grant_max_totals and app_obj.grant:
            criteria = app_obj.grant.config_json.get("criteria", [])
            grant_max_totals[gid] = max_weighted_total(criteria)
            grant_criteria_ids[gid] = [c["id"] for c in criteria]

    scored_app_ids: set[int] = set()
    for app_obj, assessment in rows:
        if assessment and assessment.scores_json and app_obj.grant_id in grant_criteria_ids:
            cids = grant_criteria_ids[app_obj.grant_id]
            if cids and all(c in assessment.scores_json for c in cids):
                scored_app_ids.add(app_obj.id)

    return render_template(
        "assessor/queue.html",
        rows=rows,
        status_filter=status_filter,
        rec_filter=rec_filter,
        grant_max_totals=grant_max_totals,
        grant_criteria_ids=grant_criteria_ids,
        scored_app_ids=scored_app_ids,
    )


@bp.get("/<int:app_id>")
@assessor_required
def application_detail(app_id: int):
    application = _get_application_or_404(app_id)
    assessment = Assessment.query.filter_by(application_id=app_id).first()
    criteria = application.grant.config_json.get("criteria", [])
    eligibility_rules = application.grant.config_json.get("eligibility", [])
    form = _CsrfForm()

    scores = assessment.scores_json if assessment else None
    elig_status = eligibility_gate_status(scores)
    decl_status = declaration_gate_status(scores)
    scoring_complete = all_criteria_scored(scores, criteria)
    can_decide, decide_reason = decision_allowed(scores, criteria)

    return render_template(
        "assessor/application_detail.html",
        application=application,
        assessment=assessment,
        criteria=criteria,
        eligibility_rules=eligibility_rules,
        max_total=max_weighted_total(criteria),
        form=form,
        elig_status=elig_status,
        decl_status=decl_status,
        scoring_complete=scoring_complete,
        can_decide=can_decide,
        decide_reason=decide_reason,
    )


@bp.post("/<int:app_id>/score")
@assessor_required
def save_score(app_id: int):
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    criteria = application.grant.config_json.get("criteria", [])
    scores: dict[str, int] = {}
    notes: dict[str, str] = {}
    errors: list[str] = []

    for c in criteria:
        cid = c["id"]
        raw_score = request.form.get("score_" + cid, "").strip()
        note = request.form.get("notes_" + cid, "").strip()

        if not raw_score:
            errors.append("Score required for: " + c["label"])
            continue
        try:
            score = int(raw_score)
        except ValueError:
            errors.append("Score must be a number for: " + c["label"])
            continue
        if score < 0 or score > c["max"]:
            errors.append("Score must be 0-{} for: {}".format(c["max"], c["label"]))
            continue
        if not note:
            errors.append("Notes required for: " + c["label"])
            continue

        scores[cid] = score
        notes[cid] = note

    if errors:
        for msg in errors:
            flash(msg, "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    assessment = _get_or_create_assessment(application)
    auto_rejected = has_auto_reject(scores, criteria)
    weighted_total = calculate_weighted_score(scores, criteria)

    old_scores = assessment.scores_json or {}
    old_notes = assessment.notes_json or {}
    # Preserve gate keys and internal metadata alongside criterion scores
    assessment.scores_json = {
        **scores,
        "_eligibility_passed": old_scores.get("_eligibility_passed"),
        "_declaration_passed": old_scores.get("_declaration_passed"),
    }
    assessment.notes_json = {
        **notes,
        "_eligibility_notes": old_notes.get("_eligibility_notes", ""),
        "_declaration_notes": old_notes.get("_declaration_notes", ""),
        "_gap_analysis": old_notes.get("_gap_analysis", ""),
        "_decision_notes": old_notes.get("_decision_notes", ""),
        "_flagged": old_notes.get("_flagged", False),
    }
    assessment.weighted_total = weighted_total
    if auto_rejected:
        assessment.recommendation = AssessmentRecommendation.REJECT

    db.session.commit()
    flash("Scores saved.", "success")
    return redirect(url_for("assessor.application_detail", app_id=app_id))


@bp.post("/<int:app_id>/eligibility-gate")
@assessor_required
def eligibility_gate(app_id: int):
    """Save the eligibility gate determination (pass/fail + notes)."""
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    raw_passed = request.form.get("eligibility_passed", "").strip()
    elig_notes = request.form.get("eligibility_notes", "").strip()

    if raw_passed not in ("true", "false"):
        flash("Select Pass or Fail for the eligibility check.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    if not elig_notes:
        flash("Eligibility notes are required.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    passed = raw_passed == "true"

    assessment = _get_or_create_assessment(application)
    old_scores = assessment.scores_json or {}
    old_notes = assessment.notes_json or {}

    assessment.scores_json = {**old_scores, "_eligibility_passed": passed}
    assessment.notes_json = {**old_notes, "_eligibility_notes": elig_notes}

    db.session.commit()

    if passed:
        flash("Eligibility check passed. Proceed to scoring.", "success")
    else:
        flash(
            "Eligibility check failed. You may record a reject decision.",
            "warning",
        )
    return redirect(url_for("assessor.application_detail", app_id=app_id))


@bp.post("/<int:app_id>/declaration-gate")
@assessor_required
def declaration_gate(app_id: int):
    """Save the declaration gate (pass/fail + notes)."""
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    raw_passed = request.form.get("declaration_passed", "").strip()
    decl_notes = request.form.get("declaration_notes", "").strip()

    if raw_passed not in ("true", "false"):
        flash("Select Pass or Fail for the declaration.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    if not decl_notes:
        flash("Declaration notes are required.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    passed = raw_passed == "true"

    assessment = _get_or_create_assessment(application)
    old_scores = assessment.scores_json or {}
    old_notes = assessment.notes_json or {}

    assessment.scores_json = {**old_scores, "_declaration_passed": passed}
    assessment.notes_json = {**old_notes, "_declaration_notes": decl_notes}

    db.session.commit()
    flash("Declaration recorded.", "success")
    return redirect(url_for("assessor.application_detail", app_id=app_id))


@bp.post("/<int:app_id>/flag")
@assessor_required
def flag_for_moderation(app_id: int):
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    assessment = _get_or_create_assessment(application)
    notes = dict(assessment.notes_json or {})
    currently_flagged = bool(notes.get("_flagged"))
    notes["_flagged"] = not currently_flagged
    assessment.notes_json = notes

    if notes["_flagged"]:
        flash("Application flagged for moderation.", "warning")
        application.status = ApplicationStatus.UNDER_REVIEW
    else:
        flash("Moderation flag removed.", "success")

    db.session.commit()
    return redirect(url_for("assessor.application_detail", app_id=app_id))


@bp.post("/<int:app_id>/decision")
@assessor_required
def record_decision(app_id: int):
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    # Enforce multi-stage gate flow
    criteria = application.grant.config_json.get("criteria", [])
    existing = Assessment.query.filter_by(application_id=app_id).first()
    scores = existing.scores_json if existing else None
    allowed, reason = decision_allowed(scores, criteria)
    if not allowed:
        flash(reason, "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    rec_value = request.form.get("recommendation", "").strip()
    decision_notes = request.form.get("decision_notes", "").strip()

    try:
        recommendation = AssessmentRecommendation(rec_value)
    except ValueError:
        flash("Invalid recommendation value.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    # If eligibility failed, only reject is valid
    elig = eligibility_gate_status(scores)
    if elig is False and recommendation != AssessmentRecommendation.REJECT:
        flash("Eligibility failed — only a reject decision is allowed.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    if not decision_notes:
        flash("Decision notes are required.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    application.status = {
        AssessmentRecommendation.FUND: ApplicationStatus.APPROVED,
        AssessmentRecommendation.REJECT: ApplicationStatus.REJECTED,
        AssessmentRecommendation.REFER: ApplicationStatus.UNDER_REVIEW,
    }[recommendation]

    assessment = _get_or_create_assessment(application)
    assessment.recommendation = recommendation
    old_notes = assessment.notes_json or {}
    assessment.notes_json = {**old_notes, "_decision_notes": decision_notes}
    assessment.completed_at = datetime.now(UTC)

    db.session.commit()
    _notify_applicant(application, recommendation, decision_notes)

    flash("Decision recorded and applicant notified.", "success")
    return redirect(url_for("assessor.application_detail", app_id=app_id))


# ---------------------------------------------------------------------------
# Monitoring plan
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict | None:
    """Extract a JSON object from a model response, stripping markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _call_claude_for_monitoring(prompt: str) -> dict | None:
    """Call Claude to generate a monitoring plan. Returns parsed JSON or None."""
    try:
        import anthropic
    except ImportError:
        log.error("anthropic SDK not installed — cannot generate monitoring plan")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        except ImportError:
            pass
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set — cannot generate monitoring plan")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    return _parse_json_response(raw)


def _build_monitoring_prompt(application: Application) -> str:
    """Build the prompt for monitoring plan generation from application data."""
    grant = application.grant
    config = grant.config_json or {}
    criteria = config.get("criteria", [])
    award_ranges = config.get("award_ranges", {})
    duration = award_ranges.get("duration_years", 3)

    org = application.organisation
    org_name = org.name if org else "Unknown"

    answers = application.answers_json or {}
    answers_block = "\n".join(
        f"  {key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in answers.items()
    ) or "  (no answers provided)"

    # Build scores block from the assessment
    assessment = Assessment.query.filter_by(application_id=application.id).first()
    scores_lines = []
    if assessment and assessment.scores_json:
        for c in criteria:
            cid = c["id"]
            score = assessment.scores_json.get(cid, "N/A")
            scores_lines.append(f"  {c['label']}: {score}/{c['max']}")
    scores_block = "\n".join(scores_lines) or "  (no scores available)"

    funding_parts = []
    if award_ranges.get("revenue_min") and award_ranges.get("revenue_max"):
        funding_parts.append(
            "Revenue: {}-{}/year".format(
                award_ranges["revenue_min"], award_ranges["revenue_max"]
            )
        )
    if award_ranges.get("capital_min") and award_ranges.get("capital_max"):
        funding_parts.append(
            "Capital: {}-{}".format(
                award_ranges["capital_min"], award_ranges["capital_max"]
            )
        )
    funding_info = "; ".join(funding_parts) or "Not specified"

    # Try to extract a project name from answers
    project_name = "Not specified"
    for page_answers in answers.values():
        if isinstance(page_answers, dict):
            for key, val in page_answers.items():
                if "project" in key.lower() and "name" in key.lower() and val:
                    project_name = str(val)
                    break

    # JSON example kept as a plain string to avoid f-string brace escaping
    json_example = (
        '{\n'
        '  "kpis": [\n'
        '    {\n'
        '      "name": "KPI name",\n'
        '      "definition": "What this measures",\n'
        '      "target": "Target value or description",\n'
        '      "baseline": "Current baseline or placeholder",\n'
        '      "evidence_source": "How it will be measured",\n'
        '      "reporting_frequency": "quarterly|annually|six-monthly",\n'
        '      "owner": "Who reports on this"\n'
        '    }\n'
        '  ],\n'
        '  "milestones": [\n'
        '    {\n'
        '      "period": "Month 1-3",\n'
        '      "description": "What should be achieved",\n'
        '      "evidence_required": "What evidence to collect"\n'
        '    }\n'
        '  ],\n'
        '  "risk_review_points": ["Month 6", "Month 12", "Month 24"],\n'
        '  "summary": "Brief monitoring plan narrative"\n'
        '}'
    )

    return (
        f"You are a monitoring and evaluation specialist for the {grant.name} programme.\n\n"
        f"## Application details\n"
        f"Organisation: {org_name}\n"
        f"Project: {project_name}\n"
        f"Funding requested: {funding_info}\n\n"
        f"## Application answers\n{answers_block}\n\n"
        f"## Scoring criteria and scores\n{scores_block}\n\n"
        f"## Task\n"
        f"Generate a monitoring plan for this approved application. "
        f"Return ONLY valid JSON with this structure:\n\n"
        f"{json_example}\n\n"
        f"Generate 4-6 KPIs covering outputs, outcomes, and system strengthening. "
        f"Include 4-6 milestones across the {duration} year programme. "
        f"Base KPIs on what the applicant has promised in their answers."
    )


@bp.get("/<int:app_id>/monitoring")
@assessor_required
def monitoring(app_id: int):
    application = _get_application_or_404(app_id)
    assessment = Assessment.query.filter_by(application_id=app_id).first()

    plan = None
    if assessment and assessment.notes_json:
        plan = assessment.notes_json.get("_monitoring_plan")

    form = _CsrfForm()
    return render_template(
        "assessor/monitoring.html",
        application=application,
        assessment=assessment,
        plan=plan,
        form=form,
    )


@bp.post("/<int:app_id>/monitoring")
@assessor_required
def generate_monitoring(app_id: int):
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    prompt = _build_monitoring_prompt(application)
    plan = _call_claude_for_monitoring(prompt)

    if plan is None:
        flash(
            "Failed to generate monitoring plan. Check that ANTHROPIC_API_KEY is set.",
            "error",
        )
        return redirect(url_for("assessor.monitoring", app_id=app_id))

    assessment = _get_or_create_assessment(application)
    old_notes = assessment.notes_json or {}
    assessment.notes_json = {**old_notes, "_monitoring_plan": plan}
    db.session.commit()

    flash("Monitoring plan generated.", "success")
    return redirect(url_for("assessor.monitoring", app_id=app_id))


# ---------------------------------------------------------------------------
# AI assessment trigger (manual, for seeded/legacy applications)
# ---------------------------------------------------------------------------


@bp.post("/<int:app_id>/run-ai")
@assessor_required
def trigger_ai(app_id: int):
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    existing = Assessment.query.filter_by(application_id=app_id).first()
    if existing is not None:
        flash("AI assessment already exists for this application.", "warning")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    from app.assessor_ai import assess_application
    assessment = assess_application(app_id)
    if assessment is None:
        flash("AI assessment failed -- check ANTHROPIC_API_KEY is set and the application has answers.", "error")
    else:
        flash("AI assessment complete.", "success")
    return redirect(url_for("assessor.application_detail", app_id=app_id))


# ---------------------------------------------------------------------------
# Allocation dashboard
# ---------------------------------------------------------------------------


@bp.get("/allocation")
@assessor_required
def allocation():
    stmt = (
        select(Application, Assessment)
        .join(Assessment, Assessment.application_id == Application.id)
        .where(Application.status != ApplicationStatus.DRAFT)
        .order_by(Assessment.weighted_total.desc())
    )
    rows = db.session.execute(stmt).all()

    total_budget = 37_000_000
    if rows:
        award_ranges = rows[0][0].grant.config_json.get("award_ranges", {})
        total_budget = award_ranges.get("total_budget", total_budget)

    return render_template(
        "assessor/allocation.html",
        rows=rows,
        total_budget=total_budget,
    )


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------


@bp.get("/users")
@assessor_required
def list_users():
    users = db.session.execute(
        select(User).where(
            User.role.in_([UserRole.ASSESSOR, UserRole.ADMIN])
        ).order_by(User.role, User.email)
    ).scalars().all()
    form = _CsrfForm()
    return render_template("assessor/users.html", users=users, form=form)


@bp.route("/users/new", methods=["GET", "POST"])
@assessor_required
def create_user():
    form = CreateAssessorForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        user = User(
            email=email,
            password_hash=generate_password_hash(form.password.data or ""),
            role=UserRole(form.role.data),
        )
        db.session.add(user)
        db.session.commit()
        flash("Account created for {}.".format(email), "success")
        return redirect(url_for("assessor.list_users"))
    return render_template("assessor/create_user.html", form=form)
