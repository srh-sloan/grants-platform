"""Flask application factory.

Stream ownership (see ``CONTRIBUTING.md``): each blueprint module listed in
``_BLUEPRINT_MODULES`` is owned by exactly one stream. New blueprints are
added to this tuple — the rest of the factory stays untouched.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from flask import Flask
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader

from app.extensions import csrf, db, limiter, login_manager

# Blueprint modules, each exporting a ``bp`` attribute. Pre-seeded so streams
# only edit their own file — no merge conflicts on this factory.
_BLUEPRINT_MODULES: tuple[str, ...] = (
    "app.public",
    "app.auth",
    "app.applicant",
    "app.assessor",
    "app.uploads",
    "app.admin",
)


def create_app(config_class: str | type = "config.Config") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    _enforce_secret_key(app)

    _install_jinja_loaders(app)
    WTFormsHelpers(app)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    # Suppress Flask-Login's default "Please log in to access this page." flash.
    # The sign-in page already explains its purpose and ``next=`` preserves the
    # originally requested URL, so the banner is redundant noise on /auth/login.
    login_manager.login_message = None
    csrf.init_app(app)
    # Rate limiter is disabled under TESTING so the auth/test suite can hammer
    # /auth/login without tripping it. Per-route limits are applied in
    # ``app.auth`` via ``@limiter.limit(...)``.
    limiter.init_app(app)
    if app.config.get("TESTING"):
        limiter.enabled = False

    # Register models + user loader on the extension (both need the app context).
    with app.app_context():
        from app import models  # noqa: F401  (registers tables)
        from app.auth import load_user  # noqa: F401  (registers @user_loader)

    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_cli(app)
    _register_external_validators(app)

    # Auto-seed in dev so `flask run` boots straight into a usable DB. Tests
    # manage their own fixtures, so skip when TESTING is set.
    if not app.config.get("TESTING"):
        _register_auto_seed(app)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    return app


def _enforce_secret_key(app: Flask) -> None:
    """Refuse to boot with the dev-only fallback secret in a prod-ish run.

    ``FLASK_DEBUG`` or ``TESTING`` opts into local/dev mode. Anything else
    (gunicorn, docker prod profile, a forgotten env in staging) must set
    ``FLASK_SECRET_KEY`` to a real value.
    """
    from config import DEV_SECRET_FALLBACK

    if app.config.get("TESTING") or app.debug:
        return
    if app.config.get("SECRET_KEY") == DEV_SECRET_FALLBACK:
        raise RuntimeError(
            "FLASK_SECRET_KEY is unset (or left at the dev fallback). Set a "
            "cryptographically random value before booting in production."
        )


def _register_external_validators(app: Flask) -> None:
    """Re-register validators that need runtime configuration (API keys, etc.).

    The validators ship with sensible defaults — ``FindThatCharity`` works
    out of the box, ``CompaniesHouse`` skips when it has no key. This hook
    lets :func:`create_app` swap in credentialled instances when the Flask
    config carries them, without every grant's form schema needing to know
    whether ops has configured the secret yet.
    """
    from app.external_validators import (
        CompaniesHouseValidator,
        register_validator,
    )

    ch_key = app.config.get("COMPANIES_HOUSE_API_KEY")
    if ch_key:
        register_validator(CompaniesHouseValidator(api_key=ch_key))


def _install_jinja_loaders(app: Flask) -> None:
    """Wire in GOV.UK Frontend Jinja templates alongside the app's own."""
    app.jinja_loader = ChoiceLoader(
        [
            PackageLoader("app"),
            PrefixLoader(
                {
                    "govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja"),
                    "govuk_frontend_wtf": PackageLoader("govuk_frontend_wtf"),
                }
            ),
        ]
    )


def _register_blueprints(app: Flask) -> None:
    for module_path in _BLUEPRINT_MODULES:
        module = importlib.import_module(module_path)
        app.register_blueprint(module.bp)


def _register_error_handlers(app: Flask) -> None:
    from flask import render_template

    @app.errorhandler(403)
    def _forbidden(_err):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def _not_found(_err):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def _server_error(_err):
        return render_template("errors/500.html"), 500


def _register_security_headers(app: Flask) -> None:
    """Set conservative security response headers on every response.

    CSP allows ``'self'`` plus inline styles (GOV.UK Frontend components
    emit a small amount of inline CSS via ``style=`` on generated SVGs).
    Scripts are ``'self'`` only; the bootstrap ``initAll()`` call lives in
    ``static/app.js``. HSTS is only meaningful behind TLS but is cheap to
    emit — browsers ignore it on plain HTTP.
    """

    @app.after_request
    def _apply_headers(response):
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if not app.debug and not app.config.get("TESTING"):
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def _register_cli(app: Flask) -> None:
    """Expose custom ``flask <command>`` subcommands.

    ``reset-db`` wraps ``seed.seed_into_session(reset=True)`` so contributors
    can blow away and rebuild the local SQLite file with one command instead
    of ``rm grants.db && uv run python seed.py``.
    """

    @app.cli.command("reset-db")
    def reset_db() -> None:
        """Drop all tables and re-seed grants, forms, and demo users."""
        from seed import seed_into_session

        seed_into_session(reset=True)


def _register_auto_seed(app: Flask) -> None:
    """Seed grants + forms + demo users on the first request.

    ``seed_into_session`` is idempotent (upserts, `db.create_all()` is a no-op
    on existing tables) so running it once per process on boot is safe. We use
    a ``before_request`` hook rather than seeding inline in ``create_app`` so
    CLI entry points (``flask reset-db``, ``python seed.py``) don't trigger a
    second seed pass on top of their own.
    """
    state = {"seeded": False}

    @app.before_request
    def _auto_seed() -> None:
        if state["seeded"]:
            return
        state["seeded"] = True
        from seed import seed_into_session

        seed_into_session(reset=False)
