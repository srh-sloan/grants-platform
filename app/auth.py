"""Authentication: login, register, logout, role-gating decorators.

**Stream ownership:** Auth & applicant UX (Stream A).

Public contract (imported by every other stream):

- :func:`load_user` — Flask-Login ``user_loader`` callback, registered by the
  app factory. Do not call directly.
- :func:`login_required` — re-exported from Flask-Login for convenience.
- :func:`applicant_required` / :func:`assessor_required` — role decorators.
  Anonymous users are redirected to the login page (preserving the target URL
  in ``?next=``); wrong-role users get a 403.

The blueprint URL prefix is fixed: ``/auth``. Do not change without
coordinating with the applicant / assessor streams.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    current_user,
    login_required,  # noqa: F401  (re-exported for cross-stream imports)
    login_user,
    logout_user,
)
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovPasswordInput,
    GovSubmitInput,
    GovTextInput,
)
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import (
    EqualTo,
    InputRequired,
    Length,
    Regexp,
    ValidationError,
)

from app.extensions import db, login_manager
from app.models import Organisation, User, UserRole

bp = Blueprint("auth", __name__, url_prefix="/auth")


# ---------------------------------------------------------------------------
# Flask-Login user loader
# ---------------------------------------------------------------------------


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    # Flask-Login expects None on lookup failure. A malformed / tampered
    # session cookie should sign the user out cleanly, not 500 the app.
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Role-gating decorators (used by applicant/assessor blueprints)
# ---------------------------------------------------------------------------


def _role_required(*roles: UserRole) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                # Defer to Flask-Login's unauthorised handler so ``next=`` is
                # preserved and the redirect respects login_manager.login_view.
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


applicant_required = _role_required(UserRole.APPLICANT)
# Admins can access the assessor area (they land there after login).
assessor_required = _role_required(UserRole.ASSESSOR, UserRole.ADMIN)


# ---------------------------------------------------------------------------
# WTForms — login / register
# ---------------------------------------------------------------------------


# Minimal pragmatic email regex. Avoids pulling in the ``email-validator``
# dep just to gate the login form on day one (see ``pyproject.toml``: adding
# a dep requires a standalone PR).
_EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_EMAIL_MESSAGE = "Enter an email address in the correct format, like name@example.com"
_PASSWORD_MIN_LENGTH = 10


class LoginForm(FlaskForm):
    """Sign-in form for existing users."""

    email = StringField(
        "Email address",
        widget=GovTextInput(),
        validators=[
            InputRequired(message="Enter your email address"),
            Length(max=255),
            Regexp(_EMAIL_REGEX, message=_EMAIL_MESSAGE),
        ],
    )
    password = PasswordField(
        "Password",
        widget=GovPasswordInput(),
        validators=[InputRequired(message="Enter your password")],
    )
    submit = SubmitField("Sign in", widget=GovSubmitInput())


class RegisterForm(FlaskForm):
    """Applicant self-registration form.

    Creates an :class:`Organisation` *and* a linked :class:`User` with the
    ``APPLICANT`` role. Assessor accounts are provisioned out-of-band via the
    seed script — there is no public assessor registration flow.
    """

    organisation_name = StringField(
        "Applicant organisation name",
        description="The legal name of the voluntary, community or faith "
        "sector organisation applying for funding.",
        widget=GovTextInput(),
        validators=[
            InputRequired(message="Enter the name of your organisation"),
            Length(max=255),
        ],
    )
    email = StringField(
        "Email address",
        description="Used to sign in and to receive updates about your application.",
        widget=GovTextInput(),
        validators=[
            InputRequired(message="Enter your email address"),
            Length(max=255),
            Regexp(_EMAIL_REGEX, message=_EMAIL_MESSAGE),
        ],
    )
    password = PasswordField(
        "Password",
        description=(
            f"Must be at least {_PASSWORD_MIN_LENGTH} characters. "
            "Use a mix of letters, numbers and symbols."
        ),
        widget=GovPasswordInput(),
        validators=[
            InputRequired(message="Enter a password"),
            Length(
                min=_PASSWORD_MIN_LENGTH,
                max=128,
                message=(
                    f"Password must be at least {_PASSWORD_MIN_LENGTH} characters"
                ),
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm password",
        widget=GovPasswordInput(),
        validators=[
            InputRequired(message="Confirm your password"),
            EqualTo("password", message="Passwords must match"),
        ],
    )
    submit = SubmitField("Create account", widget=GovSubmitInput())

    def validate_email(self, field: StringField) -> None:  # noqa: D401 — WTForms convention
        """Reject duplicate emails at the form layer so the error attaches to the field."""
        email = (field.data or "").strip().lower()
        if not email:
            return
        existing = db.session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationError("An account with this email already exists")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _role_landing(role: UserRole) -> str:
    """Return the URL a freshly-signed-in user should land on for ``role``."""
    if role == UserRole.ASSESSOR:
        return url_for("assessor.queue")
    if role == UserRole.ADMIN:
        return url_for("admin.index")
    return url_for("applicant.dashboard")


def _is_safe_next_url(target: str | None) -> bool:
    """Allow only relative, same-origin ``next=`` redirects.

    Prevents open-redirect attacks where a malicious link drops users back on a
    third-party site post-login.
    """
    if not target:
        return False
    parsed = urlparse(target)
    # Reject anything with a scheme or netloc (absolute URLs) and protocol-
    # relative paths like ``//evil.example``.
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/") and not target.startswith("//")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Sign in an existing user. GET renders the form; POST validates it."""
    if current_user.is_authenticated:
        return redirect(_role_landing(current_user.role))

    form = LoginForm()
    next_url = request.args.get("next")

    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        user = db.session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if user is not None and check_password_hash(
            user.password_hash, form.password.data or ""
        ):
            login_user(user)
            flash("You are signed in.", "success")
            if _is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(_role_landing(user.role))

        # Generic error to avoid leaking which half of the credentials is wrong
        # (and whether the email is registered at all).
        form.password.errors.append("Email or password is incorrect")

    return render_template("auth/login.html", form=form, next_url=next_url)


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Create an applicant account plus its owning organisation."""
    if current_user.is_authenticated:
        return redirect(_role_landing(current_user.role))

    form = RegisterForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()
        organisation = Organisation(
            name=(form.organisation_name.data or "").strip(),
            contact_email=email,
        )
        db.session.add(organisation)
        db.session.flush()  # populate organisation.id for the FK

        user = User(
            email=email,
            password_hash=generate_password_hash(form.password.data or ""),
            role=UserRole.APPLICANT,
            org_id=organisation.id,
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash(
            f"Account created for {organisation.name}. Start your application below.",
            "success",
        )
        return redirect(url_for("applicant.dashboard"))

    return render_template("auth/register.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    """Sign the current user out. POST-only to require CSRF."""
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("public.index"))
