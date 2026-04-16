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

from app.extensions import csrf, db, login_manager

# Blueprint modules, each exporting a ``bp`` attribute. Pre-seeded so streams
# only edit their own file — no merge conflicts on this factory.
_BLUEPRINT_MODULES: tuple[str, ...] = (
    "app.public",
    "app.auth",
    "app.applicant",
    "app.assessor",
    "app.uploads",
)


def create_app(config_class: str | type = "config.Config") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    # Register models + user loader on the extension (both need the app context).
    with app.app_context():
        from app import models  # noqa: F401  (registers tables)
        from app.auth import load_user  # noqa: F401  (registers @user_loader)

    _register_blueprints(app)
    _register_error_handlers(app)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    return app


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
