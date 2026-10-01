import re
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from efile.models import FilingDocument
from efile.services.fee_quotes import fee_inputs_token
from efile.services.waiver_documents import WAIVER_TYPE, has_waiver_document, waiver_filing_types
from efile.tests.pdf_helpers import pdf_bytes
from efile.tests.test_review_submit_flow import submission_draft as _submission_draft

payment_draft = _submission_draft

pytestmark = pytest.mark.django_db


def endpoint(draft):
    return reverse("waiver_documents", kwargs={"jurisdiction": draft.jurisdiction}) + f"?draft={draft.pk}"


def codes(_state, path, **params):
    if path.endswith("/filing_types/"):
        assert params == {"initial": "true", "category_id": "civil", "type_id": "contract"}
        return [
            {"code": "order", "name": "Order on fee waiver"},
            {"code": "internal", "name": "Fee waiver", "iscourtuseonly": True},
            {"code": "waiver", "name": "Application to waive court fees"},
            {"code": "petition", "name": "Petition"},
        ]
    if path.endswith("/document_types"):
        return [{"code": "private", "name": "Confidential"}, {"code": "public", "name": "Public"}]
    if path.endswith("/filing_components"):
        return [{"code": "lead", "name": "Lead Document"}]
    raise AssertionError(path)


@pytest.mark.parametrize(
    "name",
    [
        "Fee waiver application",
        "Affidavit of indigency",
        "In forma pauperis",
        "Motion to waive fees",
        "Application to waive court fees",
        "Application to Waive Filing and Service Fees",
        "Application Waiver of Court Fees (Civil)",
        "Indigency affidavit and request for waiver",
    ],
)
def test_recognizes_waiver_filing_types(name):
    assert WAIVER_TYPE.search(name)


@pytest.mark.parametrize(
    "name", ["Waiver of Service", "Waiver of Rights to Counsel", "Motion to Waive Final Hearing", "Waiver of feedback"]
)
def test_other_waivers_are_not_fee_waivers(name):
    assert not WAIVER_TYPE.search(name)


def test_general_fee_waiver_is_offered_before_program_specific_one(payment_draft):
    # Vermont's live list order for small claims.
    live = [
        {"code": "7481", "name": "Waiver of Service"},
        {"code": "7644", "name": "COPE - Application to Proceed In Forma Pauperis"},
        {"code": "7702", "name": "Motion to Waive Final Hearing"},
        {"code": "7764", "name": "Application to Waive Filing and Service Fees"},
    ]
    with patch("efile.services.waiver_documents._codes", return_value=live):
        assert [item["code"] for item in waiver_filing_types(payment_draft)] == ["7764", "7644"]


def test_filename_alone_does_not_hide_prompt(client, payment_draft):
    lead = payment_draft.documents.get()
    lead.name = "fee waiver.pdf"
    lead.save()
    assert not has_waiver_document(payment_draft)
    with patch("efile.views.payment.estimate_fees", return_value={}):
        page = client.get(reverse("payment", kwargs={"jurisdiction": "illinois"}))
    assert b'id="add-waiver-document"' in page.content
    lead.filing_type_name = "Affidavit of indigency"
    lead.save()
    with patch("efile.views.payment.estimate_fees", return_value={}):
        page = client.get(reverse("payment", kwargs={"jurisdiction": "illinois"}))
    assert re.search(r'id="waiver-upload-required"\s+hidden', page.content.decode())
    assert b"Add fee waiver documents</a>" not in page.content


def test_court_choices_exclude_orders_and_court_only_codes(client, payment_draft):
    with patch("efile.services.waiver_documents._codes", side_effect=codes) as lookup:
        response = client.get(endpoint(payment_draft))
    assert response.status_code == 200
    assert response.json()["selected"] == "waiver"
    assert len(response.json()["filing_types"]) == 1
    assert all("cook:law1/" in call.args[1] for call in lookup.call_args_list)


def upload_data(draft, **changes):
    return {
        "filing_type": "waiver",
        "document_type": "private",
        "fee_inputs_token": fee_inputs_token(draft),
        "document": SimpleUploadedFile("waiver.pdf", pdf_bytes(), content_type="application/pdf"),
        **changes,
    }


def confirm_data(document):
    from efile.services.document_previews import preview_fingerprint

    document.refresh_from_db()
    return {"action": "confirm", "document_id": document.pk, "preview_fingerprint": preview_fingerprint([document])}


@pytest.fixture
def storage():
    with patch("efile.views.waiver_documents.S3UploadHandler") as constructor:
        handler = constructor.return_value
        handler.validate_file.return_value = {"valid": True}
        handler._ensure_initialized.return_value = True
        handler.upload_file.return_value = {"success": True, "key": "waivers/test.pdf"}
        handler.get_public_url.return_value = "https://example.com/waiver.pdf"
        yield handler


def test_upload_preserves_case_lead_and_step_and_invalidates_quote(client, payment_draft, storage):
    lead = payment_draft.documents.get()
    original_step = payment_draft.current_step
    payment_draft.quoted_fee_total = "100"
    payment_draft.save()
    with patch("efile.services.waiver_documents._codes", side_effect=codes):
        response = client.post(endpoint(payment_draft), upload_data(payment_draft))
    assert response.status_code == 200
    added = payment_draft.documents.get(role=FilingDocument.Role.SUPPORTING)
    assert (added.filing_type_code, added.document_type_code, added.filing_component_code) == (
        "waiver",
        "private",
        "lead",
    )
    assert added.s3_key == "waivers/test.pdf"
    assert payment_draft.documents.get(role=FilingDocument.Role.LEAD).pk == lead.pk
    payment_draft.refresh_from_db()
    assert payment_draft.current_step == original_step
    assert payment_draft.court_code == "cook:law1"
    assert payment_draft.quoted_fee_total == ""
    assert response.json()["fee_inputs_token"] == fee_inputs_token(payment_draft)


@pytest.mark.parametrize(
    "changes,status",
    [({"filing_type": "invented"}, 400), ({"document_type": "invented"}, 400), ({"fee_inputs_token": "stale"}, 409)],
)
def test_invalid_or_stale_choices_never_upload(client, payment_draft, storage, changes, status):
    with patch("efile.services.waiver_documents._codes", side_effect=codes):
        response = client.post(endpoint(payment_draft), upload_data(payment_draft, **changes))
    assert response.status_code == status
    storage.upload_file.assert_not_called()
    assert payment_draft.documents.count() == 1


def test_failed_upload_is_retryable(client, payment_draft, storage):
    storage.upload_file.return_value = {"success": False}
    with patch("efile.services.waiver_documents._codes", side_effect=codes):
        response = client.post(endpoint(payment_draft), upload_data(payment_draft))
    assert response.status_code == 400
    assert payment_draft.documents.count() == 1


def test_missing_codes_do_not_guess_an_unrelated_type(client, payment_draft):
    with patch("efile.services.waiver_documents._codes", return_value=[]):
        response = client.get(endpoint(payment_draft))
    assert response.status_code == 400


def test_explicit_upload_is_saved_even_if_a_waiver_already_exists(client, payment_draft, storage):
    lead = payment_draft.documents.get()
    lead.filing_type_name = "Application for fee waiver"
    lead.save()
    with patch("efile.services.waiver_documents._codes", side_effect=codes):
        response = client.post(endpoint(payment_draft), upload_data(payment_draft))
    assert response.status_code == 200
    storage.upload_file.assert_called_once()
    assert payment_draft.documents.count() == 2


def test_upload_requires_login_and_csrf(client, payment_draft):
    assert Client().get(reverse("waiver_documents", kwargs={"jurisdiction": "illinois"})).status_code == 401
    assert Client().get(endpoint(payment_draft)).status_code == 409
    protected = Client(enforce_csrf_checks=True)
    protected.force_login(payment_draft.user)
    assert protected.post(endpoint(payment_draft), upload_data(payment_draft)).status_code == 403


def test_foreign_draft_is_not_accessible(client, payment_draft, django_user_model, storage):
    user = django_user_model.objects.create_user(username="other")
    payment_draft.user = user
    payment_draft.save()
    response = client.post(endpoint(payment_draft), upload_data(payment_draft))
    assert response.status_code in (403, 404, 409)
    storage.upload_file.assert_not_called()


@pytest.mark.parametrize("same_name", [False, True])
def test_payment_upload_stays_with_displayed_draft_through_review(client, payment_draft, storage, same_name):
    import html
    import re

    from efile.models import FilingDraft
    from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY

    if same_name:
        lead = payment_draft.documents.get()
        lead.name = "waiver.pdf"
        lead.save()
    other = FilingDraft.objects.create(user=payment_draft.user, jurisdiction="illinois")
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = other.pk
    session.save()
    payment_url = reverse("payment", kwargs={"jurisdiction": "illinois"}) + f"?draft={payment_draft.pk}"
    with patch("efile.views.payment.estimate_fees", return_value={}):
        page = client.get(payment_url)
    match = re.search(r'data-url="([^"]*waiver-documents[^\"]*)"', page.content.decode())
    assert match is not None
    upload_url = html.unescape(match.group(1))
    assert f"draft={payment_draft.pk}" in upload_url
    assert reverse("waiver_documents", kwargs={"jurisdiction": "illinois"}) in page.context["draft_scope"]["paths"]
    with patch("efile.services.waiver_documents._codes", side_effect=codes):
        uploaded = client.post(upload_url, upload_data(payment_draft))
    assert uploaded.status_code == 200
    assert other.documents.count() == 0
    with patch(
        "efile.views.payment.payment_accounts",
        return_value=[{"paymentAccountID": "wv", "paymentAccountTypeCode": "WV", "accountName": "Waiver"}],
    ):
        result = client.post(payment_url, {"selected_payment_account": "wv"})
    # The new copy is checked on Fees itself; Continue waits for that.
    assert result.status_code == 302
    assert "/payment/" in result.url
    added = payment_draft.documents.get(role=FilingDocument.Role.SUPPORTING)
    assert f'data-document-id="{added.pk}"' in uploaded.json()["check_html"]
    approved = client.post(upload_url, confirm_data(added))
    assert approved.status_code == 200
    with patch(
        "efile.views.payment.payment_accounts",
        return_value=[{"paymentAccountID": "wv", "paymentAccountTypeCode": "WV", "accountName": "Waiver"}],
    ):
        result = client.post(payment_url, {"selected_payment_account": "wv"})
    assert result.status_code == 302
    assert f"draft={payment_draft.pk}" in result.url
    with patch("efile.views.review.get_case_questions", return_value=[]):
        review = client.get(result.url)
    assert review.status_code == 200
    assert b"waiver.pdf" in review.content
    assert b"Application to waive court fees" in review.content
    assert len(review.context["documents"]) == 2
    # The actual submission payload must include it as well as the visible list.
    upload_data_for_review = review.context["upload_data"]
    assert upload_data_for_review["files"]["supporting"][0]["name"] == "waiver.pdf"
    assert upload_data_for_review["supporting_documents"][0]["filing_type"] == "waiver"


def test_unscoped_upload_cannot_silently_use_session_draft(client, payment_draft, storage):
    url = reverse("waiver_documents", kwargs={"jurisdiction": "illinois"})
    response = client.post(url, upload_data(payment_draft))
    assert response.status_code == 409
    storage.upload_file.assert_not_called()


def test_general_upload_preserves_identical_names_and_separate_storage_keys(payment_draft, storage):
    from efile.services.document_uploads import upload_files
    from efile.services.drafts import read_upload_data

    lead = payment_draft.documents.get()
    lead.name = "appearance.pdf"
    lead.s3_key = "original.pdf"
    lead.save()
    storage.upload_file.side_effect = [
        {"success": True, "key": "first-copy.pdf"},
        {"success": True, "key": "second-copy.pdf"},
    ]
    files = [SimpleUploadedFile("appearance.pdf", pdf_bytes(), content_type="application/pdf") for _ in range(2)]
    with patch("efile.services.document_uploads.S3UploadHandler", return_value=storage):
        upload_files(payment_draft, files, "illinois")
    assert payment_draft.documents.count() == 3
    assert set(payment_draft.documents.values_list("s3_key", flat=True)) == {
        "original.pdf",
        "first-copy.pdf",
        "second-copy.pdf",
    }
    assert list(payment_draft.documents.values_list("name", flat=True)) == ["appearance.pdf"] * 3
    assert len(read_upload_data(payment_draft)["files"]["supporting"]) == 2


def test_database_failure_cleans_uploaded_original_and_filing(client, payment_draft, storage):
    from django.db import DatabaseError

    from efile.tests.pdf_helpers import docx_bytes
    from efile.tests.test_document_preparation import service_response

    storage.upload_file.side_effect = [
        {"success": True, "key": "original.docx"},
        {"success": True, "key": "filing.pdf"},
    ]
    with (
        patch("efile.services.waiver_documents._codes", side_effect=codes),
        patch("efile.services.document_preparation.settings.GOTENBERG_URL", "https://synthetic.invalid"),
        patch("efile.services.document_preparation.requests.post", return_value=service_response(pdf_bytes())),
        patch("efile.views.waiver_documents.FilingDocument.objects.create", side_effect=DatabaseError("Write failed")),
        pytest.raises(DatabaseError),
    ):
        client.post(
            endpoint(payment_draft),
            upload_data(payment_draft, document=SimpleUploadedFile("waiver.docx", docx_bytes())),
        )
    assert {call.args[0] for call in storage.delete_file.call_args_list} == {"original.docx", "filing.pdf"}
    assert payment_draft.documents.count() == 1


def upload_waiver(client, draft):
    with patch("efile.services.waiver_documents._codes", side_effect=codes):
        response = client.post(endpoint(draft), upload_data(draft))
    assert response.status_code == 200
    return response, draft.documents.get(role=FilingDocument.Role.SUPPORTING)


def test_upload_is_checked_on_fees_without_leaving_it(client, payment_draft, storage):
    response, added = upload_waiver(client, payment_draft)
    body = response.json()
    assert "preview_url" not in body
    assert "data-document-confirm" in body["check_html"]
    assert "data-document-remove" in body["check_html"]
    assert added.preparation_reviewed_at is None
    with patch("efile.views.payment.estimate_fees", return_value={}):
        page = client.get(reverse("payment", kwargs={"jurisdiction": "illinois"}) + f"?draft={payment_draft.pk}")
    # A reload before confirming still shows the check on Fees, open.
    assert page.context["document_checks"][0]["document"].pk == added.pk
    assert f'data-document-id="{added.pk}"'.encode() in page.content
    assert client.post(endpoint(payment_draft), confirm_data(added)).status_code == 200
    added.refresh_from_db()
    assert added.preparation_reviewed_at is not None
    assert payment_draft.documents.get(role=FilingDocument.Role.LEAD).preparation_reviewed_at is not None


def test_confirm_rejects_a_changed_copy_and_foreign_documents(client, payment_draft, storage):
    from efile.models import FilingDraft

    _, added = upload_waiver(client, payment_draft)
    stale = confirm_data(added) | {"preview_fingerprint": "old"}
    assert client.post(endpoint(payment_draft), stale).status_code == 409
    other = FilingDraft.objects.create(user=payment_draft.user, jurisdiction="illinois")
    foreign = FilingDocument.objects.create(draft=other, role="lead", name="x.pdf", preparation="unchanged")
    assert client.post(endpoint(payment_draft), confirm_data(foreign)).status_code == 409
    added.refresh_from_db()
    foreign.refresh_from_db()
    assert added.preparation_reviewed_at is None
    assert foreign.preparation_reviewed_at is None


def test_remove_only_takes_out_a_waiver_and_reprices(
    client, payment_draft, storage, django_capture_on_commit_callbacks
):
    _, added = upload_waiver(client, payment_draft)
    lead = payment_draft.documents.get(role=FilingDocument.Role.LEAD)
    payment_draft.refresh_from_db()
    remove = {"action": "remove", "fee_inputs_token": fee_inputs_token(payment_draft)}
    assert client.post(endpoint(payment_draft), remove | {"document_id": lead.pk}).status_code == 400
    assert (
        client.post(endpoint(payment_draft), remove | {"document_id": added.pk, "fee_inputs_token": "x"}).status_code
        == 409
    )
    with (
        patch("efile.utils.s3_upload_handler.S3UploadHandler", return_value=storage),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client.post(endpoint(payment_draft), remove | {"document_id": added.pk})
    assert response.status_code == 200
    assert list(payment_draft.documents.all()) == [lead]
    payment_draft.refresh_from_db()
    assert response.json()["fee_inputs_token"] == fee_inputs_token(payment_draft)
    storage.delete_file.assert_called_with("waivers/test.pdf")


def test_payment_waits_for_unchecked_documents(client, payment_draft, storage):
    upload_waiver(client, payment_draft)
    payment_url = reverse("payment", kwargs={"jurisdiction": "illinois"}) + f"?draft={payment_draft.pk}"
    with patch(
        "efile.views.payment.payment_accounts",
        return_value=[{"paymentAccountID": "wv", "paymentAccountTypeCode": "WV", "accountName": "Waiver"}],
    ) as accounts:
        result = client.post(payment_url, {"selected_payment_account": "wv"})
    assert result.status_code == 302
    assert "/payment/" in result.url
    accounts.assert_not_called()
    payment_draft.refresh_from_db()
    assert payment_draft.selected_payment_account_id != "wv"


def test_review_sends_an_unchecked_copy_to_preview_and_back(client, payment_draft, storage):
    from efile.services.document_previews import preview_fingerprint

    upload_waiver(client, payment_draft)
    payment_draft.selected_payment_account_id = "wv"
    payment_draft.save()
    review_url = reverse("case_review", kwargs={"jurisdiction": "illinois"}) + f"?draft={payment_draft.pk}"
    bounced = client.get(review_url)
    assert bounced.status_code == 302
    assert "preview-documents" in bounced.url and "return_to=review" in bounced.url
    preview_url = reverse("preview_documents", kwargs={"jurisdiction": "illinois"}) + f"?draft={payment_draft.pk}"
    approved = client.post(
        preview_url,
        {"preview_fingerprint": preview_fingerprint(list(payment_draft.documents.all())), "return_to": "review"},
    )
    assert approved.status_code == 302
    assert "/review/" in approved.url
