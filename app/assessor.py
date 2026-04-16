"""Assessor routes: queue, application detail, scoring form, allocation dashboard.

**Stream ownership:** Assessor & scoring (Stream C).

Depends on:
- :mod:`app.scoring` — pure scoring helpers (Stream C owns).
- :mod:`app.auth` — ``assessor_required`` decorator (Stream A owns).

URL prefix: ``/assess``. Stable contracts:

- ``GET /assess/``                           → queue (filterable)
- ``GET /assess/<application_id>``           → detail view + scoring form
- ``POST /assess/<application_id>/score``    → save/submit scores
- ``GET /assess/allocation``                 → ranked allocation dashboard
"""

from __future__ import annotations

from flask import Blueprint

from app.auth import assessor_required

bp = Blueprint("assessor", __name__, url_prefix="/assess")


@bp.get("/")
@assessor_required
def queue():
    """Placeholder queue. Stream C: list submitted applications with filters."""
    return ("Assessor queue not implemented yet", 501)
