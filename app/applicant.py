"""Applicant routes: dashboard, application runner, review, submit.

**Stream ownership:** Auth & applicant UX (Stream A) owns the dashboard and
review/submit routes. The form-rendering routes delegate to
:mod:`app.forms_runner` (Stream B).

URL prefix: ``/apply``. Stable contracts:

- ``GET  /apply/``                        → :func:`dashboard`
- ``GET  /apply/<grant_slug>/start``      → create/open a draft application
- ``GET  /apply/<app_id>/<page_id>``      → render form page
- ``POST /apply/<app_id>/<page_id>``      → save page as draft
- ``GET  /apply/<app_id>/review``         → read-only summary
- ``POST /apply/<app_id>/submit``         → submit application
"""

from __future__ import annotations

from flask import Blueprint

from app.auth import applicant_required

bp = Blueprint("applicant", __name__, url_prefix="/apply")


@bp.get("/")
@applicant_required
def dashboard():
    """Placeholder dashboard. Stream A: list my applications and their status."""
    return ("Applicant dashboard not implemented yet", 501)
