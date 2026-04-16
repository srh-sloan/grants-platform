"""Applicant routes: dashboard, application runner, review, submit.

**Stream ownership:** Auth & applicant UX (Stream A) owns the dashboard and
review / submit routes. The form-rendering routes delegate to
:mod:`app.forms_runner` (Stream B) and render
``templates/forms/page.html`` / ``templates/forms/summary.html`` — both
shared templates owned by Stream B.

URL prefix: ``/apply``. Stable contracts:

- ``GET  /apply/``                          → :func:`dashboard`
- ``GET  /apply/<grant_slug>/start``        → :func:`start` (create/open a draft)
- ``GET  /apply/<app_id>/tasks``            → :func:`task_list` (section status + submit)
- ``GET  /apply/<app_id>/<page_id>``        → :func:`form_page` (render)
- ``POST /apply/<app_id>/<page_id>``        → :func:`save_page` (save draft)
- ``GET  /apply/<app_id>/review``           → :func:`review` (read-only summary)
- ``POST /apply/<app_id>/submit``           → :func:`submit`
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from werkzeug.datastructures import MultiDict

from app.auth import applicant_required
from app.extensions import db
from app.external_validators import validate_page_external
from app.forms_runner import (
    evaluate_eligibility,
    get_page,
    list_pages,
    merge_page_answers,
    next_page_id,
    prev_page_id,
    validate_page,
)
from app.models import (
    Application,
    ApplicationStatus,
    Form,
    FormKind,
    Grant,
    GrantStatus,
)
from app.uploads import UploadRejected, list_documents, save_upload

bp = Blueprint("applicant", __name__, url_prefix="/apply")


# ---------------------------------------------------------------------------
# Tiny CSRF-only form — used on POST buttons ("Start", "Submit", "Sign out")
# where no other fields are collected. Flask-WTF's ``CSRFProtect`` already
# enforces CSRF on every POST; wrapping the button in a FlaskForm is just the
# clearest way to render the hidden token from the template.
# ---------------------------------------------------------------------------


class _ActionForm(FlaskForm):
    """Hidden-CSRF-token-only form."""


# ---------------------------------------------------------------------------
# Authorisation + lookup helpers
# ---------------------------------------------------------------------------


def _get_owned_application(app_id: int) -> Application:
    """Load an application or 404 if it isn't owned by the current user's org."""
    application = db.session.get(Application, app_id)
    if application is None or application.org_id != current_user.org_id:
        abort(404)
    return application


def _application_form(application: Application) -> Form:
    """Resolve the applicant form bound to an application (by grant + version)."""
    form = db.session.execute(
        select(Form).where(
            Form.grant_id == application.grant_id,
            Form.kind == FormKind.APPLICATION,
            Form.version == application.form_version,
        )
    ).scalar_one_or_none()
    if form is None:
        abort(500)
    return form


def _latest_application_form_for_grant(grant: Grant) -> Form:
    """Pick the highest-version application form for ``grant``, or 500 if none."""
    form = (
        db.session.execute(
            select(Form)
            .where(Form.grant_id == grant.id, Form.kind == FormKind.APPLICATION)
            .order_by(Form.version.desc())
        )
        .scalars()
        .first()
    )
    if form is None:
        abort(500)
    return form


def _page_errors_across_form(application: Application, form: Form) -> dict[str, dict[str, str]]:
    """Return ``{page_id: errors_dict}`` for every page that has validation errors.

    Used on the review page so the applicant can see what's still missing
    before submitting, and by :func:`submit` to refuse submission when
    anything is outstanding.

    External-validator checks are deliberately *not* re-run here — they're
    enforced at page-save time. Re-running them on every review/submit view
    would mean hammering third-party registers every time the applicant
    opens the summary, and a transient outage would silently undo an already-
    saved green check. If a validator's verdict needs to be re-verified at
    submit time, that belongs in the submit handler (where we accept a
    single round-trip).
    """
    result: dict[str, dict[str, str]] = {}
    answers = application.answers_json or {}
    for page in list_pages(form.schema_json):
        errors = validate_page(page, answers.get(page["id"], {}))
        if errors:
            result[page["id"]] = errors
    return result


def _run_external_validators(page: dict, submitted: dict) -> dict[str, str]:
    """Run external validators for ``page`` if the feature is enabled.

    Wraps :func:`app.external_validators.validate_page_external` with a
    config-flag check so airgapped / test environments skip the I/O entirely
    without the schema needing to change.

    Returns an empty dict when the feature is disabled or no field on the
    page declares a validator.
    """
    if not current_app.config.get("EXTERNAL_VALIDATORS_ENABLED", False):
        return {}
    errors, metadata = validate_page_external(page, submitted)
    if metadata:
        # Stash the matched organisation names so the review summary can
        # show "Verified: <name>" next to each validated answer. We don't
        # block on this — it's purely informational.
        current_app.logger.debug("external validator metadata: %s", metadata)
    return errors


def _first_page_id(form: Form) -> str:
    """First page ID in the schema, or 500 if the schema has no pages."""
    pages = list_pages(form.schema_json)
    if not pages:
        abort(500)
    return pages[0]["id"]


def _resume_page_id(application: Application, form: Form) -> str:
    """Return the first page with validation errors, or the first page if all are OK.

    Gives the applicant a sensible "pick up where you left off" redirect
    target when they revisit the start URL.
    """
    errors = _page_errors_across_form(application, form)
    for page in list_pages(form.schema_json):
        if page["id"] in errors:
            return page["id"]
    return _first_page_id(form)


# ---------------------------------------------------------------------------
# Form submission extraction — maps the HTML POST body onto a
# ``{field_id: value}`` dict that ``forms_runner.validate_page`` expects.
# ---------------------------------------------------------------------------


def _extract_field_values(page: dict, form_data: MultiDict) -> dict[str, object]:
    """Read submitted values for each field on ``page`` from ``form_data``."""
    extracted: dict[str, object] = {}
    for field in page.get("fields") or []:
        fid = field["id"]
        ftype = field.get("type")

        if ftype == "checkbox":
            # A checkbox field with ``options`` is a multi-select; without
            # options it's a single declaration checkbox (agree-terms, etc.).
            if field.get("options"):
                extracted[fid] = form_data.getlist(fid)
            else:
                extracted[fid] = fid in form_data
        elif ftype == "file":
            # Real uploads come through request.files and are processed
            # separately in save_page. We return None here; save_page
            # supplements with the existing saved answer before validation.
            extracted[fid] = None
        elif ftype == "date":
            # govukDateInput submits three separate fields: fid-day, fid-month, fid-year.
            day   = (form_data.get(f"{fid}-day")   or "").strip()
            month = (form_data.get(f"{fid}-month") or "").strip()
            year  = (form_data.get(f"{fid}-year")  or "").strip()
            if day and month and year:
                extracted[fid] = f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                extracted[fid] = ""  # empty string triggers required validation
        else:
            value = form_data.get(fid)
            if isinstance(value, str):
                value = value.strip()
            extracted[fid] = value
    return extracted


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.get("/")
@applicant_required
def dashboard():
    """Applicant dashboard — my applications + grants available to start."""
    applications = (
        db.session.execute(
            select(Application)
            .where(Application.org_id == current_user.org_id)
            .options(selectinload(Application.grant))
            .order_by(Application.updated_at.desc())
        )
        .scalars()
        .all()
    )

    open_grants = (
        db.session.execute(
            select(Grant).where(Grant.status == GrantStatus.OPEN).order_by(Grant.name)
        )
        .scalars()
        .all()
    )
    # Only offer a "Start application" CTA for grants the org hasn't already
    # opened a draft / submission against.
    existing_grant_ids = {app.grant_id for app in applications}
    available_grants = [g for g in open_grants if g.id not in existing_grant_ids]

    return render_template(
        "applicant/dashboard.html",
        applications=applications,
        available_grants=available_grants,
        start_form=_ActionForm(),
    )


def _eligibility_form_for_grant(grant: Grant) -> Form | None:
    """Return the eligibility form for ``grant``, or None if none is defined."""
    return db.session.execute(
        select(Form)
        .where(Form.grant_id == grant.id, Form.kind == FormKind.ELIGIBILITY)
        .order_by(Form.version.desc())
    ).scalars().first()


@bp.get("/<grant_slug>/eligibility")
@applicant_required
def eligibility(grant_slug: str):
    """Render the eligibility pre-check form for ``grant_slug``."""
    grant = db.session.execute(
        select(Grant).where(Grant.slug == grant_slug)
    ).scalar_one_or_none()
    if grant is None:
        abort(404)
    if grant.status != GrantStatus.OPEN:
        flash(
            f"{grant.name} is not currently open for applications.",
            "error",
        )
        return redirect(url_for("applicant.dashboard"))

    elig_form = _eligibility_form_for_grant(grant)
    if elig_form is None:
        # Grant has no eligibility form — skip straight to start.
        return redirect(url_for("applicant.start", grant_slug=grant.slug))

    page = list_pages(elig_form.schema_json)[0]
    # The page.html template expects an ``application`` with ``grant`` — use a
    # lightweight stand-in since no application exists yet.
    fake_app = SimpleNamespace(id=None, grant=grant)

    return render_template(
        "forms/page.html",
        form=elig_form,
        application=fake_app,
        page=page,
        answers={},
        errors={},
        back_url=url_for("applicant.dashboard"),
        action_url=url_for("applicant.eligibility_post", grant_slug=grant.slug),
        csrf_form=_ActionForm(),
        all_pages=None,
        current_index=0,
        form_caption="Eligibility check",
    )


@bp.post("/<grant_slug>/eligibility")
@applicant_required
def eligibility_post(grant_slug: str):
    """Validate the eligibility form and evaluate eligibility rules."""
    grant = db.session.execute(
        select(Grant).where(Grant.slug == grant_slug)
    ).scalar_one_or_none()
    if grant is None:
        abort(404)
    if grant.status != GrantStatus.OPEN:
        flash(
            f"{grant.name} is not currently open for applications.",
            "error",
        )
        return redirect(url_for("applicant.dashboard"))

    elig_form = _eligibility_form_for_grant(grant)
    if elig_form is None:
        return redirect(url_for("applicant.start", grant_slug=grant.slug))

    page = list_pages(elig_form.schema_json)[0]
    submitted = _extract_field_values(page, request.form)
    errors = validate_page(page, submitted)

    if errors:
        fake_app = SimpleNamespace(id=None, grant=grant)
        rendered = render_template(
            "forms/page.html",
            form=elig_form,
            application=fake_app,
            page=page,
            answers=submitted,
            errors=errors,
            back_url=url_for("applicant.dashboard"),
            action_url=url_for(
                "applicant.eligibility_post", grant_slug=grant.slug
            ),
            csrf_form=_ActionForm(),
            all_pages=None,
            current_index=0,
            form_caption="Eligibility check",
        )
        return rendered, 400

    eligibility_result = evaluate_eligibility(
        grant.config_json["eligibility"], submitted
    )

    return render_template(
        "forms/eligibility_result.html",
        result=eligibility_result,
        grant=grant,
        continue_url=url_for("applicant.start", grant_slug=grant.slug),
        check_url=url_for("applicant.eligibility", grant_slug=grant.slug),
    )


@bp.get("/<grant_slug>/start")
@applicant_required
def start(grant_slug: str):
    """Open (or create) the applicant's draft for ``grant_slug`` and redirect to page 1.

    Idempotent: repeated visits reuse the existing draft so applicants can
    bookmark and come back later.
    """
    grant = db.session.execute(
        select(Grant).where(Grant.slug == grant_slug)
    ).scalar_one_or_none()
    if grant is None:
        abort(404)
    if grant.status != GrantStatus.OPEN:
        flash(
            f"{grant.name} is not currently open for applications.",
            "error",
        )
        return redirect(url_for("applicant.dashboard"))

    application = db.session.execute(
        select(Application).where(
            Application.org_id == current_user.org_id,
            Application.grant_id == grant.id,
        )
    ).scalar_one_or_none()

    if application is None:
        form = _latest_application_form_for_grant(grant)
        application = Application(
            org_id=current_user.org_id,
            grant_id=grant.id,
            form_version=form.version,
            status=ApplicationStatus.DRAFT,
            answers_json={},
        )
        db.session.add(application)
        db.session.commit()
    else:
        form = _application_form(application)

    # All applications land on the task list. The task list handles routing
    # to the review page for submitted applications.
    return redirect(url_for("applicant.task_list", app_id=application.id))


def _render_form_page(
    application: Application,
    form: Form,
    page: dict,
    answers: dict,
    errors: dict[str, str],
    status_code: int = 200,
):
    """Shared renderer for GET form_page + POST save_page with validation errors."""
    back_page = prev_page_id(form.schema_json, page["id"])
    back_url = (
        url_for("applicant.form_page", app_id=application.id, page_id=back_page)
        if back_page
        else url_for("applicant.dashboard")
    )
    action_url = url_for(
        "applicant.form_page", app_id=application.id, page_id=page["id"]
    )
    all_pages = list_pages(form.schema_json)
    current_index = next(
        (i for i, p in enumerate(all_pages) if p["id"] == page["id"]),
        0,
    )
    # Template contract (see templates/forms/page.html docstring): the progress
    # line renders only when both page_number and total_pages are provided.
    rendered = render_template(
        "forms/page.html",
        form=form,
        application=application,
        page=page,
        answers=answers,
        errors=errors,
        back_url=back_url,
        action_url=action_url,
        csrf_form=_ActionForm(),
        page_number=current_index + 1,
        total_pages=len(all_pages),
    )
    return (rendered, status_code) if status_code != 200 else rendered


@bp.get("/<int:app_id>/tasks")
@applicant_required
def task_list(app_id: int):
    """Task list — section-by-section status overview and submit entry point."""
    application = _get_owned_application(app_id)
    form = _application_form(application)

    pages = list_pages(form.schema_json)
    answers = application.answers_json or {}
    errors_by_page = _page_errors_across_form(application, form)

    tasks = []
    for page in pages:
        pid = page["id"]
        page_answers = answers.get(pid, {})
        if not page_answers:
            status = "not_started"
        elif pid in errors_by_page:
            status = "in_progress"
        else:
            status = "completed"
        tasks.append({
            "page": page,
            "status": status,
            "href": url_for("applicant.form_page", app_id=app_id, page_id=pid)
            if application.status == ApplicationStatus.DRAFT else None,
        })

    all_complete = (
        application.status == ApplicationStatus.DRAFT
        and not errors_by_page
        and all(t["status"] == "completed" for t in tasks)
    )

    return render_template(
        "applicant/task_list.html",
        application=application,
        tasks=tasks,
        all_complete=all_complete,
        submit_form=_ActionForm(),
    )


@bp.get("/<int:app_id>/<page_id>")
@applicant_required
def form_page(app_id: int, page_id: str):
    """Render a single page of the applicant form, pre-filled with any saved answers."""
    application = _get_owned_application(app_id)
    # Submitted applications are read-only — push the user to the review page.
    if application.status != ApplicationStatus.DRAFT:
        return redirect(url_for("applicant.review", app_id=app_id))

    form = _application_form(application)
    page = get_page(form.schema_json, page_id)
    if page is None:
        abort(404)

    saved_for_page = (application.answers_json or {}).get(page_id, {})
    return _render_form_page(application, form, page, saved_for_page, errors={})


@bp.post("/<int:app_id>/<page_id>")
@applicant_required
def save_page(app_id: int, page_id: str):
    """Validate and persist one page of answers. Redirect to the next page on success."""
    application = _get_owned_application(app_id)
    if application.status != ApplicationStatus.DRAFT:
        # Don't allow late edits once submitted — treat it like a 409, but
        # redirect to the review page for a clean user experience.
        flash(
            "This application has already been submitted and can no longer be edited.",
            "error",
        )
        return redirect(url_for("applicant.review", app_id=app_id))

    form = _application_form(application)
    page = get_page(form.schema_json, page_id)
    if page is None:
        abort(404)

    submitted = _extract_field_values(page, request.form)
    existing_page = (application.answers_json or {}).get(page_id, {})

    # Process file uploads BEFORE validation so validate_page sees the
    # filename as the field value (it just needs a truthy string, not the
    # actual bytes). Upload errors are collected separately.
    upload_errors: dict[str, str] = {}
    for field in page.get("fields") or []:
        if field.get("type") != "file":
            continue
        fid = field["id"]
        file_storage = request.files.get(fid)
        if file_storage and file_storage.filename:
            try:
                # Stage the Document row; only committed if the full page is valid.
                doc = save_upload(application, kind=fid, file_storage=file_storage)
                submitted[fid] = doc.filename
            except UploadRejected as exc:
                upload_errors[fid] = str(exc)
        else:
            # No new file — use the previously saved filename (from a prior
            # upload) or any text value submitted in the form (covers tests
            # and hidden-input replay patterns).
            submitted[fid] = (
                existing_page.get(fid)
                or (request.form.get(fid) or "").strip()
                or None
            )

    errors = {**validate_page(page, submitted), **upload_errors}

    # Layer external-register checks on top of basic validation. External
    # validators run in their own module so the form runner stays pure; we
    # merge the results here rather than passing I/O into ``validate_page``.
    # A field that already failed required / word-limit checks is never
    # sent off to an external API — no point asking the Charity Commission
    # whether a blank value exists.
    external_errors = _run_external_validators(page, submitted)
    for field_id, message in external_errors.items():
        errors.setdefault(field_id, message)

    if errors:
        # Roll back any staged Document rows — the page wasn't fully valid.
        db.session.rollback()
        return _render_form_page(
            application, form, page, submitted, errors=errors, status_code=400
        )

    application.answers_json = merge_page_answers(
        application.answers_json or {}, page_id, submitted
    )
    db.session.commit()

    # Return to the task list after every successful page save.
    # The task list shows what's done and what remains, and is the entry point
    # for the submit action — keeping review separate from submission.
    return redirect(url_for("applicant.task_list", app_id=app_id))


@bp.get("/<int:app_id>/review")
@applicant_required
def review(app_id: int):
    """Read-only summary of every answer, plus a Submit button."""
    application = _get_owned_application(app_id)
    form = _application_form(application)
    documents = list_documents(application.id)

    return render_template(
        "applicant/review.html",
        application=application,
        form=form,
        schema=form.schema_json,
        answers=application.answers_json or {},
        documents=documents,
    )


@bp.post("/<int:app_id>/submit")
@applicant_required
def submit(app_id: int):
    """Transition a completed draft application to SUBMITTED."""
    application = _get_owned_application(app_id)
    if application.status != ApplicationStatus.DRAFT:
        flash("This application has already been submitted.", "info")
        return redirect(url_for("applicant.task_list", app_id=app_id))

    form = _application_form(application)
    errors_by_page = _page_errors_across_form(application, form)
    if errors_by_page:
        flash(
            "You still have sections with missing or invalid answers. "
            "Complete them before submitting.",
            "error",
        )
        return redirect(url_for("applicant.task_list", app_id=app_id))

    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = datetime.now(UTC)
    db.session.commit()

    # Enqueue AI assessment on the background pool so the applicant's
    # submission response isn't held up by the Claude round-trip. Failures to
    # *queue* (missing key, grant has no criteria) are logged but never shown
    # to the applicant — the assessor sees a row with FAILED status if the
    # Claude call itself errors out later. See :mod:`app.assessor_ai`.
    try:
        from app.assessor_ai import queue_assessment
        queue_assessment(application.id)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "AI assessment could not be queued for app %s: %s", application.id, exc
        )

    flash(
        f"Application submitted to {application.grant.name}. "
        "We'll be in touch once it has been assessed.",
        "success",
    )
    return redirect(url_for("applicant.task_list", app_id=app_id))
