"""Confirming or removing a newly prepared copy on the page it was added to."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft
from efile.services.document_previews import preview_fingerprint
from efile.services.fee_quotes import fee_inputs_token
from efile.tests.test_review_submit_flow import submission_draft as _submission_draft

draft = _submission_draft

pytestmark = pytest.mark.django_db


def checks(draft):
    return reverse("document_checks", kwargs={"jurisdiction": draft.jurisdiction}) + f"?draft={draft.pk}"


@pytest.fixture
def added(draft):
    return FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.SUPPORTING,
        sort_order=1,
        name="exhibit.pdf",
        s3_key="supporting/exhibit.pdf",
        preparation="unchanged",
    )


def confirm(document, **changes):
    document.refresh_from_db()
    return {
        "action": "confirm",
        "document_id": document.pk,
        "preview_fingerprint": preview_fingerprint([document]),
        **changes,
    }


def test_confirming_marks_only_that_copy_checked(client, draft, added):
    response = client.post(checks(draft), confirm(added))
    assert response.status_code == 200
    added.refresh_from_db()
    assert added.preparation_reviewed_at is not None


def test_a_changed_unprepared_or_foreign_copy_is_not_confirmed(client, draft, added):
    assert client.post(checks(draft), confirm(added, preview_fingerprint="old")).status_code == 409
    FilingDocument.objects.filter(pk=added.pk).update(preparation="")
    assert client.post(checks(draft), confirm(added)).status_code == 409
    other = FilingDraft.objects.create(user=draft.user, jurisdiction="illinois")
    foreign = FilingDocument.objects.create(draft=other, role="lead", name="x.pdf", preparation="unchanged")
    assert client.post(checks(draft), confirm(foreign)).status_code == 409
    added.refresh_from_db()
    foreign.refresh_from_db()
    assert added.preparation_reviewed_at is None
    assert foreign.preparation_reviewed_at is None


def test_removing_takes_out_a_supporting_file_and_reprices(client, draft, added, django_capture_on_commit_callbacks):
    lead = draft.documents.get(role=FilingDocument.Role.LEAD)
    draft.quoted_fee_total = "100"
    draft.save()
    remove = {"action": "remove"}
    assert client.post(checks(draft), remove | {"document_id": lead.pk}).status_code == 400
    storage = MagicMock()
    storage.delete_file.return_value = {"success": True}
    with (
        patch("efile.utils.s3_upload_handler.S3UploadHandler", return_value=storage),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client.post(checks(draft), remove | {"document_id": added.pk})
    assert response.status_code == 200
    assert list(draft.documents.all()) == [lead]
    draft.refresh_from_db()
    assert draft.quoted_fee_total == ""
    assert response.json()["fee_inputs_token"] == fee_inputs_token(draft)
    storage.delete_file.assert_called_with("supporting/exhibit.pdf")


def test_checks_need_a_signed_in_named_filing_and_csrf(client, draft, added):
    unscoped = reverse("document_checks", kwargs={"jurisdiction": "illinois"})
    assert Client().post(unscoped, confirm(added)).status_code == 401
    # Someone else's draft is refused before the view, by the draft scope.
    assert Client().post(checks(draft), confirm(added)).status_code == 409
    assert client.post(unscoped, confirm(added)).status_code == 409
    assert client.get(checks(draft)).status_code == 405
    protected = Client(enforce_csrf_checks=True)
    protected.force_login(draft.user)
    assert protected.post(checks(draft), confirm(added)).status_code == 403
