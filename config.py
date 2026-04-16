"""App configuration.

Values come from environment variables, with sensible defaults for local dev.
Production secrets must be set via env; never commit real keys.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'grants.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH: int = 20 * 1024 * 1024  # 20 MB per upload


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    UPLOAD_FOLDER: str = str(BASE_DIR / "uploads_test")
