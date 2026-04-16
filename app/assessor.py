"""Assessor routes: queue, application detail, scoring, decision, allocation.

**Stream ownership:** Assessor & scoring (Stream C).

URL prefix: ``/assess``.

Routes
------
GET  /assess/                     -- application queue (filterable)
GET  /assess/<app_id>             -- detail: answers + AI assessment + scoring form
POST /assess/<app_id>/score       -- save manual scores
POST /assess/<app_id>/flag        -- flag for moderation review
POST /assess/<app_id>/decision    -- record final decision + notify applicant
GET  /assess/allocation           -- ranked allocation dashboard
"""

from __future__ import annotations

import logging
import os
import smtplib
import textwrap
from datetime import UTC, datetime
from email.mime.text import MIMEText

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from sqlalchemy import select

from app.auth import assessor_required
from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    Assessment,
    AssessmentRecommendation,
)
from app.scoring import calculate_weighted_score, has_auto_reject, max_weighted_total

log = logging.getLogger(__name__)

bp = Blueprint("assessor", __name__, url_prefix="/assess")


# ---------------------------------------------------------------------------
# Tiny CSRF-bearing forms (fields rendered manually in templates)
# ---------------------------------------------------------------------------


class _CsrfForm(FlaskForm):
    """No fields -- used only for the hidden CSRF token on POST buttons."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_application_or_404(app_id: int) -> Application:
    application = db.session.get(Application, app_id)
    if application is None or application.status == ApplicationStatus.DRAFT:
        abort(404)
    return application


def _get_or_create_assessment(application: Application) -> Assessment:
    """Return the existing assessment, or create a bare one for manual scoring."""
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
            if decision_notes
            else ""
        ),
        contact_email=application.grant.config_json.get("contact_email", "grants@communities.gov.uk"),
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
# Routes
# ---------------------------------------------------------------------------


@bp.get("/")
@assessor_required
def queue():
    """Application queue -- all non-draft applications with optional filters."""
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
            (a, s)
            for a, s in rows
            if s and s.recommendation and s.recommendation.value == rec_filter
        ]

    return render_template(
        "assessor/queue.html",
        rows=rows,
        status_filter=status_filter,
        rec_filter=rec_filter,
    )


@bp.get("/<int:app_id>")
@assessor_required
def application_detail(app_id: int):
    """Detail view: applicant answers, AI assessment, manual scoring form, decision."""
    application = _get_application_or_404(app_id)
    assessment = Assessment.query.filter_by(application_id=app_id).first()
    criteria = application.grant.config_json.get("criteria", [])
    form = _CsrfForm()

    return render_template(
        "assessor/application_detail.html",
        application=application,
        assessment=assessment,
        criteria=criteria,
        max_total=max_weighted_total(criteria),
        form=form,
    )


@bp.post("/<int:app_id>/score")
@assessor_required
def save_score(app_id: int):
    """Save manual assessor scores for each criterion."""
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

    old_notes = assessment.notes_json or {}
    assessment.scores_json = scores
    assessment.notes_json = {
        **notes,
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


@bp.post("/<int:app_id>/flag")
@assessor_required
def flag_for_moderation(app_id: int):
    """Toggle the moderation flag on an assessment."""
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    assessment = _get_or_create_assessment(application)
    notes = dict(assessment.notes_json or {})
    currently_flagged = bool(notes.get("_flagged"))
    notes["_flagged"] = not currently_flagged
    assessment.notes_json = notes
    db.session.commit()

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
    """Record a final funding decision and notify the applicant by email."""
    application = _get_application_or_404(app_id)
    form = _CsrfForm()
    if not form.validate_on_submit():
        abort(400)

    rec_value = request.form.get("recommendation", "").strip()
    decision_notes = request.form.get("decision_notes", "").strip()

    try:
        recommendation = AssessmentRecommendation(rec_value)
    except ValueError:
        flash("Invalid recommendation value.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    if not decision_notes:
        flash("Decision notes are required.", "error")
        return redirect(url_for("assessor.application_detail", app_id=app_id))

    # Update application status
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


@bp.get("/allocation")
@assessor_required
def allocation():
    """Ranked allocation dashboard: all assessed applications sorted by score."""
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
