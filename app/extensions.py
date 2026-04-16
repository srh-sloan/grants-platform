"""Flask extension singletons.

Kept in a separate module so blueprints can import `db` without importing the
app factory (which would create a circular import).
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
