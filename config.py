"""App configuration.

Values come from environment variables, with sensible defaults for local dev.
Production secrets must be set via env; never commit real keys.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_DEFAULT_SECRET = "dev-secret-change-me"  # noqa: S105 — sentinel only, never used in prod


class Config:
    _raw_secret = os.environ.get("FLASK_SECRET_KEY", _DEFAULT_SECRET)
    if _raw_secret == _DEFAULT_SECRET and os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError(
            "FLASK_SECRET_KEY must be set to a strong random value in production. "
            "Run: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    SECRET_KEY: str = _raw_secret

    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'grants.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH: int = 20 * 1024 * 1024  # 20 MB per upload

    # Session security — cookies are HttpOnly + SameSite=Lax always; Secure
    # is only forced in production so local dev (plain HTTP) still works.
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = os.environ.get("FLASK_ENV") == "production"
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SECURE: bool = os.environ.get("FLASK_ENV") == "production"
    # Idle sessions expire after 1 hour; each request refreshes the timer.
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(hours=1)
    SESSION_REFRESH_EACH_REQUEST: bool = True

    # Feature switch for external registry lookups (Charity Commission,
    # Companies House, etc.). Defaults on in production so new grants can
    # opt into validators purely via their form schema. Flip off for
    # offline / airgapped runs.
    EXTERNAL_VALIDATORS_ENABLED: bool = (
        os.environ.get("EXTERNAL_VALIDATORS_ENABLED", "1").lower()
        not in ("0", "false", "no")
    )
    # Companies House API key — optional. When unset the Companies House
    # validator reports itself as "skipped" and the FindThatCharity
    # aggregator is the sole fall-back.
    COMPANIES_HOUSE_API_KEY: str | None = os.environ.get("COMPANIES_HOUSE_API_KEY")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    UPLOAD_FOLDER: str = str(BASE_DIR / "uploads_test")
    # Keep tests hermetic: no outbound HTTP unless a specific test opts in.
    EXTERNAL_VALIDATORS_ENABLED = False
