"""Tests for document upload handling (Stream D — P2.3)."""

from __future__ import annotations

import os
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    Organisation,
    User,
    UserRole,
)
from app.uploads import UploadRejected, list_documents, save_upload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(
    content: bytes = b"test content",
    filename: str = "test.pdf",
    content_type: str = "application/pdf",
) -> FileStorage:
    return FileStorage(
        stream=BytesIO(content),
        filename=filename,
        content_type=content_type,
    )


def _login(client, user):
    """Log in *user* via the test client session."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)


# ---------------------------------------------------------------------------
# save_upload
# ---------------------------------------------------------------------------


class TestSaveUpload:
    def test_creates_document_row(self, app, submitted_application):
        with app.app_context():
            doc = save_upload(submitted_application, "budget", _make_file())
            assert doc.id is not None
            assert doc.application_id == submitted_application.id
            assert doc.kind == "budget"
            assert doc.filename == "test.pdf"
            assert doc.storage_path == f"{submitted_application.id}/budget/test.pdf"

    def test_writes_file_to_disk(self, app, submitted_application):
        with app.app_context():
            doc = save_upload(
                submitted_application,
                "budget",
                _make_file(content=b"hello world"),
            )
            upload_folder = app.config["UPLOAD_FOLDER"]
            full_path = os.path.join(upload_folder, doc.storage_path)
            assert os.path.isfile(full_path)
            with open(full_path, "rb") as f:
                assert f.read() == b"hello world"

    def test_rejects_empty_filename(self, app, submitted_application):
        with app.app_context(), pytest.raises(UploadRejected):
            save_upload(submitted_application, "budget", _make_file(filename=""))

    def test_rejects_none_filename(self, app, submitted_application):
        """A FileStorage with filename=None should also be rejected."""
        with app.app_context():
            fs = FileStorage(stream=BytesIO(b"x"), filename=None)
            with pytest.raises(UploadRejected):
                save_upload(submitted_application, "budget", fs)

    def test_sanitises_filename(self, app, submitted_application):
        """Dangerous path components are stripped by secure_filename."""
        with app.app_context():
            doc = save_upload(
                submitted_application,
                "la_letter",
                _make_file(filename="../../../etc/passwd"),
            )
            assert ".." not in doc.storage_path
            assert "etc" in doc.storage_path or "passwd" in doc.storage_path


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_returns_uploaded_docs(self, app, submitted_application):
        with app.app_context():
            save_upload(submitted_application, "budget", _make_file(filename="a.pdf"))
            save_upload(submitted_application, "plan", _make_file(filename="b.pdf"))
            docs = list_documents(submitted_application.id)
            assert len(docs) == 2
            assert docs[0].filename == "a.pdf"
            assert docs[1].filename == "b.pdf"

    def test_empty_for_no_docs(self, app, submitted_application):
        with app.app_context():
            assert list_documents(submitted_application.id) == []


# ---------------------------------------------------------------------------
# serve_document (download route)
# ---------------------------------------------------------------------------


class TestServeDocument:
    def test_requires_auth(self, app, client, submitted_application):
        """Unauthenticated users are redirected to login."""
        with app.app_context():
            doc = save_upload(submitted_application, "budget", _make_file())
            doc_id = doc.id
        resp = client.get(f"/uploads/{doc_id}")
        assert resp.status_code in (301, 302)
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_applicant_can_access_own(self, app, client, applicant_user, submitted_application):
        with app.app_context():
            doc = save_upload(
                submitted_application,
                "budget",
                _make_file(content=b"secret data"),
            )
            doc_id = doc.id
        _login(client, applicant_user)
        resp = client.get(f"/uploads/{doc_id}")
        assert resp.status_code == 200
        assert resp.data == b"secret data"

    def test_applicant_cannot_access_others(self, app, client, applicant_user, submitted_application):
        """An applicant from a different org gets 403."""
        with app.app_context():
            doc = save_upload(submitted_application, "budget", _make_file())
            doc_id = doc.id

            # Create a second org + user
            other_org = Organisation(
                name="Other Org",
                contact_name="Other",
                contact_email="other@example.com",
            )
            db.session.add(other_org)
            db.session.flush()
            other_user = User(
                email="other@test.com",
                password_hash="x",
                role=UserRole.APPLICANT,
                org_id=other_org.id,
            )
            db.session.add(other_user)
            db.session.commit()
            other_user_id = other_user.id

        _login(client, type("U", (), {"id": other_user_id})())
        resp = client.get(f"/uploads/{doc_id}")
        assert resp.status_code == 403

    def test_assessor_can_access_submitted(self, app, client, assessor_user, submitted_application):
        with app.app_context():
            doc = save_upload(submitted_application, "budget", _make_file())
            doc_id = doc.id
        _login(client, assessor_user)
        resp = client.get(f"/uploads/{doc_id}")
        assert resp.status_code == 200

    def test_assessor_cannot_access_draft(self, app, client, assessor_user, seeded_grant, applicant_user):
        """Assessors should not see documents on draft applications."""
        with app.app_context():
            draft_app = Application(
                org_id=applicant_user.org_id,
                grant_id=seeded_grant.id,
                form_version=1,
                status=ApplicationStatus.DRAFT,
                answers_json={},
            )
            db.session.add(draft_app)
            db.session.commit()
            doc = save_upload(draft_app, "budget", _make_file())
            doc_id = doc.id

        _login(client, assessor_user)
        resp = client.get(f"/uploads/{doc_id}")
        assert resp.status_code == 403

    def test_returns_404_for_missing_doc(self, client, applicant_user):
        _login(client, applicant_user)
        resp = client.get("/uploads/99999")
        assert resp.status_code == 404
