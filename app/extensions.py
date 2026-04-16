"""Flask extension singletons.

Kept in a separate module so blueprints can import `db` without importing the
app factory (which would create a circular import).
"""

from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
# In-memory store is fine for a single-process prototype; switch ``storage_uri``
# to redis/memcached before running multiple gunicorn workers in production.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
