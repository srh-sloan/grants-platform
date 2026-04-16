"""Shared authorisation helpers.

Cross-stream ownership / role predicates live here so applicant and uploads
blueprints don't drift on what "owns an application" means. Pure functions
only — no I/O. Call sites decide what to do on a false result (404 for
applicant routes, 403 for the upload serve).
"""

from __future__ import annotations

from app.models import Application, User, UserRole


def is_application_owned_by(application: Application, user: User) -> bool:
    """True if ``user`` is an applicant whose org owns ``application``."""
    return (
        user.role == UserRole.APPLICANT
        and application.org_id is not None
        and application.org_id == user.org_id
    )
