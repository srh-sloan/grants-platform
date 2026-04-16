"""App configuration.

Values come from environment variables, with sensible defaults for local dev.
Production secrets must be set via env; never commit real keys.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Dev-only fallback. The factory refuses to boot with this value unless
# ``FLASK_DEBUG`` or ``TESTING`` is set, so a forgotten env var in prod
# fails loudly instead of signing sessions with a guessable secret.
DEV_SECRET_FALLBACK = "dev-secret-do-not-use-in-prod"


class Config:
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", DEV_SECRET_FALLBACK)
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'grants.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH: int = 20 * 1024 * 1024  # 20 MB per upload

    # Feature switch for external registry lookups (Charity Commission,
    # Companies House, etc.). Defaults on in production so new grants can
    # opt into validators purely via their form schema. Flip off for
    # offline / airgapped runs.
    EXTERNAL_VALIDATORS_ENABLED: bool = os.environ.get(
        "EXTERNAL_VALIDATORS_ENABLED", "1"
    ).lower() not in ("0", "false", "no")
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
