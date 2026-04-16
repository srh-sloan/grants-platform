"""File upload handling — save applicant documents, list them, serve downloads.

**Stream ownership:** Platform, data & uploads (Stream D).

Streams A and C consume the public helpers below; nobody else writes
``Document`` rows or touches ``UPLOAD_FOLDER`` directly.

Public contract (pinned in ``CONTRIBUTING.md``):

- :func:`save_upload(application, kind, file_storage) -> Document`
- :func:`list_documents(application_id) -> list[Document]`
- :func:`document_url(doc) -> str`

Phase 0 ships these as stubs so Streams A + C can import them without waiting
for Stream D. The stubs raise :class:`NotImplementedError` rather than
returning fake data — if a test hits one, the signal is obvious.

Download route lives at ``/uploads/<document_id>`` (authz-gated). The
blueprint is registered from ``app.__init__._BLUEPRINT_MODULES`` once Stream
D lands it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — import-cycle guard
    from werkzeug.datastructures import FileStorage

    from app.models import Application, Document


class UploadRejected(ValueError):
    """Raised when an upload fails validation (size, MIME, etc)."""


def save_upload(
    application: Application,
    kind: str,
    file_storage: FileStorage,
) -> Document:
    """Persist ``file_storage`` to disk and create a ``Document`` row.

    Storage layout: ``UPLOAD_FOLDER/<application_id>/<kind>/<filename>``.
    Raises :class:`UploadRejected` on validation failure (size, MIME, extension).
    Stream D replaces this stub in Phase 2.
    """
    raise NotImplementedError("Stream D: save_upload not implemented yet")


def list_documents(application_id: int) -> list[Document]:
    """Return all documents attached to ``application_id`` ordered by upload time.

    Empty list when the application has no documents. Stream D replaces this
    stub in Phase 2 — until then, review / detail pages render an empty
    "Supporting documents" section.
    """
    return []


def document_url(doc: Document) -> str:
    """URL for the authz-gated download route for ``doc``."""
    raise NotImplementedError("Stream D: document_url not implemented yet")
