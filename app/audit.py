"""Structured audit logging for sensitive actions.

Writes JSON-formatted entries to the ``grants.audit`` logger so they can be
shipped to any log aggregator (stdout in dev, a sidecar in prod). No new DB
table is needed — the logger is a thin wrapper around Python's stdlib logging.

Usage::

    from app.audit import audit_log

    audit_log("LOGIN_SUCCESS", user_id=user.id, email=user.email)
    audit_log("DECISION_RECORDED", user_id=current_user.id,
              application_id=app_id, recommendation=rec.value)

Every entry includes: ``event``, ``user_id``, ``ip``, ``ts``, plus any extra
kwargs. ``ip`` is taken from the current request context when available.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from flask import has_request_context, request

_audit = logging.getLogger("grants.audit")
# Ensure audit events are always emitted even if the root logger is quiet.
if not _audit.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit.addHandler(_handler)
    _audit.setLevel(logging.INFO)
    _audit.propagate = False


def audit_log(event: str, *, user_id: int | None = None, **extra: Any) -> None:
    """Emit a structured audit log entry."""
    entry: dict[str, Any] = {
        "event": event,
        "ts": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        "ip": request.remote_addr if has_request_context() else None,
    }
    entry.update(extra)
    _audit.info(json.dumps(entry, default=str))
