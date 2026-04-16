"""Flask application factory."""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader

from app.extensions import csrf, db, login_manager


def create_app(config_class: str | type = "config.Config") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    _install_jinja_loaders(app)
    WTFormsHelpers(app)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    csrf.init_app(app)

    # Import models so they're registered with SQLAlchemy's metadata.
    with app.app_context():
        from app import models  # noqa: F401

        @login_manager.user_loader
        def _load_user(user_id: str):
            return db.session.get(models.User, int(user_id))

    _register_blueprints(app)

    # Ensure upload folder exists in dev.
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
    from app.public import bp as public_bp

    app.register_blueprint(public_bp)
