"""Database models and shared enums.

The schema is deliberately grant-agnostic:

- Grant-specific rules (eligibility, scoring criteria, weights, award ranges,
  timeline) live inside :attr:`Grant.config_json`.
- Form shape (pages, fields, validation) lives inside :attr:`Form.schema_json`.
- Applicant answers are keyed to the form schema and stored in
  :attr:`Application.answers_json`.
- Assessor scores are keyed to the grant criteria IDs and stored in
  :attr:`Assessment.scores_json` / :attr:`Assessment.notes_json`.

See ``CLAUDE.md`` for the full contract shapes.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from flask_login import UserMixin
from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db


def _utcnow() -> datetime:
    """Timezone-aware UTC `now`, used as the column default for timestamps."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Shared enums — imported by views, not re-declared
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    APPLICANT = "applicant"
    ASSESSOR = "assessor"
    ADMIN = "admin"


class GrantStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    DRAFT = "draft"


class FormKind(str, enum.Enum):
    APPLICATION = "application"
    ASSESSMENT = "assessment"
    ELIGIBILITY = "eligibility"


class ApplicationStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AssessmentRecommendation(str, enum.Enum):
    FUND = "fund"
    REJECT = "reject"
    REFER = "refer"


class AssessmentStatus(str, enum.Enum):
    """Lifecycle of an AI assessment row.

    Human-scored assessments start as :attr:`COMPLETED` (they're written in one
    shot by the scoring form). AI assessments move through
    :attr:`PENDING` → :attr:`IN_PROGRESS` → :attr:`COMPLETED` or
    :attr:`FAILED` as the background worker progresses.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Organisation(db.Model):
    __tablename__ = "organisations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(db.String(255))
    contact_email: Mapped[str | None] = mapped_column(db.String(255))
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="organisation")
    applications: Mapped[list[Application]] = relationship(back_populates="organisation")

    @validates("name", "contact_name")
    def _strip_whitespace(self, _key: str, value: str | None) -> str | None:
        """Trim leading/trailing whitespace on applicant-entered names.

        Applies to every write path (register form, seed scripts, direct model
        edits) so the DB never holds a padded value.
        """
        if isinstance(value, str):
            return value.strip()
        return value


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False), nullable=False
    )
    org_id: Mapped[int | None] = mapped_column(db.ForeignKey("organisations.id"))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    organisation: Mapped[Organisation | None] = relationship(back_populates="users")
    assessments: Mapped[list[Assessment]] = relationship(back_populates="assessor")

    # Convenience predicates used across blueprints.
    @property
    def is_applicant(self) -> bool:
        return self.role == UserRole.APPLICANT

    @property
    def is_assessor(self) -> bool:
        return self.role == UserRole.ASSESSOR

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class Grant(db.Model):
    __tablename__ = "grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(db.String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    status: Mapped[GrantStatus] = mapped_column(
        SAEnum(GrantStatus, native_enum=False), nullable=False, default=GrantStatus.OPEN
    )
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    forms: Mapped[list[Form]] = relationship(back_populates="grant")
    applications: Mapped[list[Application]] = relationship(back_populates="grant")

    @property
    def summary(self) -> str | None:
        return self.config_json.get("summary") if self.config_json else None


class Form(db.Model):
    __tablename__ = "forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(db.ForeignKey("grants.id"), nullable=False)
    kind: Mapped[FormKind] = mapped_column(
        SAEnum(FormKind, native_enum=False), nullable=False
    )
    version: Mapped[int] = mapped_column(db.Integer, nullable=False, default=1)
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    grant: Mapped[Grant] = relationship(back_populates="forms")


class Application(db.Model):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(db.ForeignKey("organisations.id"), nullable=False)
    grant_id: Mapped[int] = mapped_column(db.ForeignKey("grants.id"), nullable=False)
    form_version: Mapped[int] = mapped_column(db.Integer, nullable=False, default=1)
    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, native_enum=False),
        nullable=False,
        default=ApplicationStatus.DRAFT,
    )
    answers_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow, nullable=False
    )

    organisation: Mapped[Organisation] = relationship(back_populates="applications")
    grant: Mapped[Grant] = relationship(back_populates="applications")
    documents: Mapped[list[Document]] = relationship(back_populates="application")
    assessments: Mapped[list[Assessment]] = relationship(back_populates="application")


class Document(db.Model):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        db.ForeignKey("applications.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(db.String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(db.String(512), nullable=False)
    filename: Mapped[str] = mapped_column(db.String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    application: Mapped[Application] = relationship(back_populates="documents")


class Assessment(db.Model):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        db.ForeignKey("applications.id"), nullable=False
    )
    assessor_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False)
    scores_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    weighted_total: Mapped[int | None] = mapped_column(db.Integer)
    recommendation: Mapped[AssessmentRecommendation | None] = mapped_column(
        SAEnum(AssessmentRecommendation, native_enum=False)
    )
    # Background-task lifecycle for AI-generated assessments. Defaults to
    # COMPLETED so rows created synchronously by human assessors (and legacy
    # AI rows from before async landed) remain in a valid terminal state
    # without any backfill.
    status: Mapped[AssessmentStatus] = mapped_column(
        SAEnum(AssessmentStatus, native_enum=False),
        nullable=False,
        default=AssessmentStatus.COMPLETED,
    )
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    # Truncated exception message when :attr:`status` is FAILED. Surfaced in
    # the assessor UI so a human can decide whether to retry.
    error_message: Mapped[str | None] = mapped_column(db.String(500))

    application: Mapped[Application] = relationship(back_populates="assessments")
    assessor: Mapped[User] = relationship(back_populates="assessments")

    @property
    def is_pending_ai(self) -> bool:
        """True while the AI worker has a row queued or in-flight."""
        return self.status in (AssessmentStatus.PENDING, AssessmentStatus.IN_PROGRESS)
