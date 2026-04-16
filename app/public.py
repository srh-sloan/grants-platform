"""Public (unauthenticated) routes: landing page and GOV.UK Frontend assets."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template, send_from_directory
from sqlalchemy import select

from app.extensions import db
from app.models import Grant, GrantStatus

bp = Blueprint("public", __name__)


@bp.get("/")
def index():
    open_grants = (
        db.session.execute(
            select(Grant).where(Grant.status == GrantStatus.OPEN).order_by(Grant.name)
        )
        .scalars()
        .all()
    )
    return render_template("public/index.html", grants=open_grants)


@bp.get("/assets/<path:filename>")
def govuk_assets(filename: str):
    """Serve the GOV.UK Frontend fonts/images bundle at the paths the CSS expects."""
    assets_dir = Path(current_app.static_folder) / "assets"
    return send_from_directory(assets_dir, filename)
