import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from efile.models import FilingDocument, FilingDraft
from efile.services.document_previews import preview_fingerprint
from efile.services.document_uploads import upload_files
from efile.services.drafts import read_upload_data, write_upload_data
from efile.tests.pdf_helpers import pdf_bytes
from efile.tests.test_document_extractions import authorize

pytestmark = pytest.mark.django_db


@pytest.fixture
def preview_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="preview-filer", tyler_jurisdiction="vermont")
    draft = FilingDraft.objects.create(user=user, jurisdiction="vermont", workflow_version=2)
    authorize(client, draft)
    FilingDocument.objects.create(
        draft=draft,
        role="lead",
        name="filing.pdf",
        s3_key="private/filing.pdf",
        original_s3_key="private/original.docx",
        original_filename="original.docx",
        preparation="converted",
    )
    return draft


def url(name, draft, **kwargs):
    return reverse(name, kwargs={"jurisdiction": draft.jurisdiction, **kwargs}) + f"?draft={draft.pk}"


def approve(client, draft, **overrides):
    documents = list(draft.documents.all())
    return client.post(
        url("preview_documents", draft),
        {
            "preview_fingerprint": preview_fingerprint(documents),
            "reviewed_document": [str(doc.pk) for doc in documents],
            **overrides,
        },
    )


def test_review_is_required_and_requires_each_current_document(client, preview_draft):
    doc = preview_draft.documents.get()
    redirect = client.get(url("extraction_review", preview_draft))
    assert redirect.status_code == 302 and "preview-documents" in redirect.url
    assert approve(client, preview_draft, reviewed_document=[]).status_code == 200
    doc.refresh_from_db()
    assert doc.preparation_reviewed_at is None
    assert approve(client, preview_draft, preview_fingerprint="stale").status_code == 200
    assert approve(client, preview_draft).status_code == 302
    doc.refresh_from_db()
    assert doc.preparation_reviewed_at is not None
    assert client.get(url("extraction_review", preview_draft)).status_code == 200


def test_original_and_filing_bytes_are_separate_and_not_cached(client, preview_draft):
    doc = preview_draft.documents.get()
    content = pdf_bytes()
    handler = MagicMock()
    handler.bucket_name = "private"
    handler.s3_client.get_object.side_effect = lambda **kw: {
        "Body": io.BytesIO(content if kw["Key"] == doc.s3_key else b"original Word bytes")
    }
    with patch("efile.views.document_previews.S3UploadHandler", return_value=handler):
        filing = client.get(url("document_content", preview_draft, document_id=doc.pk))
        assert filing.status_code == 200
        assert b"".join(filing.streaming_content) == content
        assert filing["Content-Type"] == "application/pdf"
        assert filing["Cache-Control"] == "private, no-store"
        original = client.get(url("document_content", preview_draft, document_id=doc.pk) + "&original=1")
        assert b"".join(original.streaming_content) == b"original Word bytes"
        assert original["Content-Disposition"].startswith("attachment;")


def test_preview_cannot_read_another_users_or_another_drafts_document(client, preview_draft, django_user_model):
    doc = preview_draft.documents.get()
    other = FilingDraft.objects.create(user=preview_draft.user, jurisdiction="vermont")
    with patch("efile.views.document_previews.S3UploadHandler") as storage:
        response = client.get(url("document_content", other, document_id=doc.pk))
        assert response.status_code == 404
        other_user = django_user_model.objects.create_user(username="other-filer", tyler_jurisdiction="vermont")
        client.force_login(other_user)
        assert client.get(url("document_content", preview_draft, document_id=doc.pk)).status_code in {403, 409}
    storage.assert_not_called()


def test_previews_require_sign_in(client, preview_draft):
    doc = preview_draft.documents.get()
    client.logout()
    response = client.get(reverse("document_content", kwargs={"jurisdiction": "vermont", "document_id": doc.pk}))
    assert response.status_code == 401


def test_submission_cannot_bypass_preview(client, preview_draft):
    with patch("efile.views.submission.forward_final_filing") as forward:
        response = client.post(reverse("submit_final_filing"), data="{}", content_type="application/json")
    assert response.status_code == 412
    assert "Preview" in response.json()["error"]
    forward.assert_not_called()
    preview_draft.refresh_from_db()
    assert preview_draft.status == FilingDraft.Status.DRAFT


def test_later_uploads_are_all_or_nothing_and_leave_existing_approvals(preview_draft):
    doc = preview_draft.documents.get()
    doc.preparation_reviewed_at = timezone.now()
    doc.save()
    handler = MagicMock()
    handler.upload_file.return_value = {"success": True, "key": "new.pdf"}
    handler.get_public_url.return_value = "https://s3.example/new.pdf"
    with patch("efile.services.document_uploads.S3UploadHandler", return_value=handler):
        with pytest.raises(ValueError, match="could not be read"):
            upload_files(
                preview_draft,
                [SimpleUploadedFile("valid.pdf", pdf_bytes()), SimpleUploadedFile("bad.pdf", b"invalid")],
                "vermont",
            )
    assert preview_draft.documents.count() == 1
    doc.refresh_from_db()
    assert doc.preparation_reviewed_at is not None
    handler.delete_file.assert_called_once_with("new.pdf")


def test_original_and_approval_survive_supporting_row_rebuilds(preview_draft):
    supporting = FilingDocument.objects.create(
        draft=preview_draft,
        role="supporting",
        name="support.pdf",
        original_filename="support.docx",
        s3_key="support.pdf",
        original_s3_key="support.docx",
        preparation="converted",
        preparation_reviewed_at=timezone.now(),
    )
    wire = read_upload_data(preview_draft)
    # Browser-supplied preparation approval and original key must be ignored.
    wire["files"]["supporting"][0].update(preparation_reviewed_at="forged", original_s3_key="forged")
    write_upload_data(preview_draft, wire)
    saved = preview_draft.documents.get(role="supporting")
    assert saved.original_s3_key == "support.docx"
    assert saved.original_filename == "support.docx"
    assert saved.preparation_reviewed_at == supporting.preparation_reviewed_at


def test_preview_return_destinations_are_restricted(client, preview_draft):
    response = approve(client, preview_draft, return_to="https://attacker.example")
    assert "extraction-review" in response.url
    assert "attacker" not in response.url
    response = approve(client, preview_draft, return_to="payment")
    assert "/payment/" in response.url
