"""File upload handling — save applicant documents, list them, serve downloads.

**Stream ownership:** Platform, data & uploads (Stream D).

Streams A and C consume the public helpers below; nobody else writes
``Document`` rows or touches ``UPLOAD_FOLDER`` directly.

Public contract (pinned in ``CONTRIBUTING.md``):

- :func:`save_upload(application, kind, file_storage) -> Document`
- :func:`list_documents(application_id) -> list[Document]`
- :func:`document_url(doc) -> str`

Download route lives at ``/uploads/<doc_id>`` (authz-gated).
"""

from __future__ import annotations

import os

from flask import Blueprint, abort, current_app, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Application, ApplicationStatus, Document, UserRole

bp = Blueprint("uploads", __name__, url_prefix="/uploads")


class UploadRejected(ValueError):
    """Raised when an upload fails validation (size, MIME, etc)."""


# ---------------------------------------------------------------------------
# Public helpers (consumed by Streams A and C)
# ---------------------------------------------------------------------------


def save_upload(
    application: Application,
    kind: str,
    file_storage: FileStorage,
) -> Document:
    """Persist *file_storage* to disk and create a ``Document`` row.

    Storage layout: ``UPLOAD_FOLDER/<application_id>/<kind>/<filename>``.
    Raises :class:`UploadRejected` on validation failure.
    """
    original_filename = file_storage.filename or ""
    safe_name = secure_filename(original_filename)
    if not safe_name:
        raise UploadRejected("Filename is empty or contains only unsafe characters")

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    relative_dir = os.path.join(str(application.id), kind)
    absolute_dir = os.path.join(upload_folder, relative_dir)
    os.makedirs(absolute_dir, exist_ok=True)

    relative_path = os.path.join(relative_dir, safe_name)
    absolute_path = os.path.join(upload_folder, relative_path)

    file_storage.save(absolute_path)

    doc = Document(
        application_id=application.id,
        kind=kind,
        storage_path=relative_path,
        filename=original_filename,
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def list_documents(application_id: int) -> list[Document]:
    """Return all documents for *application_id*, ordered by upload time."""
    return (
        db.session.query(Document)
        .filter_by(application_id=application_id)
        .order_by(Document.uploaded_at)
        .all()
    )


def document_url(doc: Document) -> str:
    """URL for the authz-gated download route for *doc*."""
    return url_for("uploads.serve_document", doc_id=doc.id)


# ---------------------------------------------------------------------------
# Download route (authz-gated)
# ---------------------------------------------------------------------------


@bp.get("/<int:doc_id>")
@login_required
def serve_document(doc_id: int):
    """Serve a document file after checking authorization.

    - Applicants may only download documents attached to their own org's
      applications.
    - Assessors may download documents for any non-draft application.
    """
    doc = db.session.get(Document, doc_id)
    if doc is None:
        abort(404)

    application = doc.application

    if current_user.role == UserRole.APPLICANT:
        if application.org_id != current_user.org_id:
            abort(403)
    elif current_user.role in (UserRole.ASSESSOR, UserRole.ADMIN):
        if application.status == ApplicationStatus.DRAFT:
            abort(403)
    else:
        abort(403)

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(
        upload_folder,
        doc.storage_path,
        download_name=doc.filename,
    )
