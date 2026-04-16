"""Authentication: login, logout, register, role-gating decorators.

**Stream ownership:** Auth & applicant UX (Stream A).

Public contract (imported by every other stream):

- :func:`load_user` — Flask-Login ``user_loader`` callback, registered by the
  app factory. Do not call directly.
- :func:`login_required` — re-exported from Flask-Login for convenience.
- :func:`applicant_required` / :func:`assessor_required` — role decorators.
  Compose with :func:`login_required` is implicit: the decorators short-circuit
  anonymous users to the login page.

The blueprint URL prefix is fixed: ``/auth``. Do not change without
coordinating with the applicant / assessor streams.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, abort, redirect, url_for
from flask_login import current_user, login_required  # noqa: F401  (re-exported)

from app.extensions import db, login_manager
from app.models import User, UserRole

bp = Blueprint("auth", __name__, url_prefix="/auth")


# ---------------------------------------------------------------------------
# Flask-Login user loader
# ---------------------------------------------------------------------------


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Role-gating decorators (used by applicant/assessor blueprints)
# ---------------------------------------------------------------------------


def _role_required(role: UserRole) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


applicant_required = _role_required(UserRole.APPLICANT)
assessor_required = _role_required(UserRole.ASSESSOR)


# ---------------------------------------------------------------------------
# Placeholder routes — Stream A replaces these with real login/register/logout
# ---------------------------------------------------------------------------


@bp.get("/login")
def login():
    """Placeholder login page. Stream A replaces with WTForms login form."""
    return ("Login not implemented yet", 501)


@bp.post("/logout")
def logout():
    """Placeholder logout. Stream A replaces with Flask-Login logout_user()."""
    return ("Logout not implemented yet", 501)


@bp.get("/register")
def register():
    """Placeholder register page. Stream A replaces with WTForms register form."""
    return ("Register not implemented yet", 501)
