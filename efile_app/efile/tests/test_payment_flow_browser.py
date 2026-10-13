"""Opt-in Chromium validation of the Fees screen. Uses only synthetic documents.

Run with PAYMENT_FLOW_BROWSER_TESTS=1 uv run pytest -s efile/tests/test_payment_flow_browser.py
S3 and the court's code lists are test doubles; uploads, previews, and PDF.js are real.
"""

import io
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.tests.pdf_helpers import pdf_bytes
from efile.tests.test_document_extractions import authorize
from efile.tests.test_waiver_documents import codes

ACCOUNTS = [
    {"paymentAccountID": "wv-1", "paymentAccountTypeCode": "WV", "accountName": "Fee waiver"},
    {"paymentAccountID": "cc-1", "paymentAccountTypeCode": "CC", "accountName": "Visa"},
]


def payment_ready_draft(user, objects):
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        current_step="payment",
        existing_case="new",
        court_code="cook:law1",
        court_name="Circuit Court of Cook County",
        case_category_code="civil",
        case_category_name="Civil",
        case_type_code="contract",
        case_type_name="Contract",
        document_checklist_acknowledged=True,
    )
    key = f"lead/{draft.pk}"
    objects[key] = pdf_bytes("Synthetic petition")
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        name="Petition.pdf",
        original_filename="Petition.pdf",
        s3_key=key,
        preparation="unchanged",
        preparation_reviewed_at="2026-01-01T00:00:00Z",
        filing_type_code="petition",
        filing_type_name="Petition",
        document_type_code="public",
        document_type_name="Public",
        filing_component_code="lead",
        filing_component_name="Lead document",
    )
    FilingParty.objects.create(
        draft=draft,
        role="filer",
        party_type="PLA",
        party_type_name="Plaintiff/Petitioner",
        is_filing_party=True,
        first_name="Jordan",
        last_name="Taylor",
        email="jordan@example.com",
        address_line_1="123 Main Street",
        city="Springfield",
        state="IL",
        zip_code="62701",
    )
    return draft


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.getenv("PAYMENT_FLOW_BROWSER_TESTS"), reason="Opt-in: requires Chromium")
def test_fees_screen_flows_in_browser(live_server, client, django_user_model, tmp_path):
    user = django_user_model.objects.create_user(username="synthetic-fees", tyler_jurisdiction="illinois")
    objects = {}
    first = payment_ready_draft(user, objects)
    second = payment_ready_draft(user, objects)
    third = payment_ready_draft(user, objects)
    authorize(client, first)
    handler = MagicMock()
    handler.bucket_name = "synthetic"
    handler.validate_file.return_value = {"valid": True}
    handler._ensure_initialized.return_value = True

    def store(file, **kwargs):
        key = f"{kwargs['file_type']}/{len(objects)}"
        objects[key] = file.read()
        return {"success": True, "key": key}

    handler.upload_file.side_effect = store

    def delete(key):
        objects.pop(key, None)
        return {"success": True}

    handler.delete_file.side_effect = delete
    handler.get_public_url.side_effect = lambda key: f"https://synthetic.invalid/{key}"
    handler.s3_client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    files = {
        "waiverFile": ("waiver.pdf", pdf_bytes("Application to waive court fees", pages=2)),
        "wrongFile": ("wrong.pdf", pdf_bytes("Not the waiver")),
        "invalidFile": ("broken.pdf", b"not a PDF"),
    }
    paths = {}
    for key, (name, content) in files.items():
        (tmp_path / key).mkdir()
        file = tmp_path / key / name
        file.write_bytes(content)
        paths[key] = str(file)
    payment = reverse("payment", kwargs={"jurisdiction": "illinois"})
    evidence = Path(os.getenv("PAYMENT_FLOW_EVIDENCE_DIR", str(tmp_path / "evidence")))
    config = tmp_path / "browser.json"
    config.write_text(
        json.dumps(
            {
                "baseUrl": live_server.url,
                "cookie": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "evidence": str(evidence),
                "paymentUrl": f"{payment}?draft={first.pk}",
                "secondPaymentUrl": f"{payment}?draft={second.pk}",
                "previewUrl": reverse("preview_documents", kwargs={"jurisdiction": "illinois"}) + f"?draft={first.pk}",
                "uploadUrl": reverse("upload_documents", kwargs={"jurisdiction": "illinois"}) + f"?draft={first.pk}",
                "checklistUrl": reverse("document_checklist", kwargs={"jurisdiction": "illinois"})
                + f"?draft={third.pk}",
                **paths,
            }
        )
    )
    with (
        patch("efile.views.waiver_documents.S3UploadHandler", return_value=handler),
        patch("efile.views.document_previews.S3UploadHandler", return_value=handler),
        patch("efile.services.document_uploads.S3UploadHandler", return_value=handler),
        patch("efile.views.upload_documents.S3UploadHandler", return_value=handler),
        patch("efile.utils.s3_upload_handler.S3UploadHandler", return_value=handler),
        patch("efile.services.waiver_documents._codes", side_effect=codes),
        patch("efile.views.payment.estimate_fees", return_value={}),
        patch("efile.views.payment.payment_accounts", return_value=ACCOUNTS),
        patch("efile.views.review.get_case_questions", return_value=[]),
        patch("efile.views.document_checklist.draft_unavailable_message", return_value=""),
    ):
        result = subprocess.run(
            ["node", "tests/payment-flow-browser.js", str(config)],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=240,
        )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    first.refresh_from_db()
    assert first.selected_payment_account_id == "wv-1"
    assert [doc.name for doc in first.documents.order_by("role", "sort_order")] == ["Petition.pdf", "waiver.pdf"]
    assert not first.documents.filter(preparation_reviewed_at__isnull=True).exists()
    # The wrong file and the copy removed from another tab are gone, with their bytes.
    assert [doc.name for doc in second.documents.order_by("role", "sort_order")] == ["Petition.pdf", "waiver.pdf"]
    # The checklist kept the file it checked and dropped the one it removed.
    assert [doc.name for doc in third.documents.order_by("role", "sort_order")] == ["Petition.pdf", "waiver.pdf"]
    assert not third.documents.filter(preparation_reviewed_at__isnull=True).exists()
    assert sorted(key.split("/")[0] for key in objects) == [
        "document",
        "lead",
        "lead",
        "lead",
        "supporting",
        "supporting",
    ]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.getenv("WAIVER_HIERARCHY_BROWSER_TESTS"), reason="Opt-in: requires Chromium")
@pytest.mark.parametrize("scenario", ["specific", "waiver", "application"])
def test_illinois_waiver_hierarchy_in_browser(live_server, client, django_user_model, tmp_path, scenario):
    user = django_user_model.objects.create_user(username=f"waiver-{scenario}", tyler_jurisdiction="illinois")
    objects = {}
    filing = payment_ready_draft(user, objects)
    authorize(client, filing)
    handler = MagicMock()
    handler.bucket_name = "synthetic"
    handler.validate_file.return_value = {"valid": True}
    handler._ensure_initialized.return_value = True

    def store(file, **kwargs):
        key = f"{kwargs['file_type']}/{len(objects)}"
        objects[key] = file.read()
        return {"success": True, "key": key}

    handler.upload_file.side_effect = store
    handler.get_public_url.side_effect = lambda key: f"https://synthetic.invalid/{key}"
    handler.s3_client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    catalog = [
        {"code": "application", "name": "Application"},
        {"code": "waiver", "name": "Waiver"},
        {"code": "specific", "name": "Application Waiver of Court Fees (Civil)"},
    ][: {"specific": 3, "waiver": 2, "application": 1}[scenario]]
    submitted = []

    def answer(payload):
        result = MagicMock(status_code=200, headers={"Content-Type": "application/json"}, text=json.dumps(payload))
        result.json.return_value = payload
        return result

    def get(url, **kwargs):
        if "/payments/payment-accounts" in url:
            return answer(ACCOUNTS)
        if url.endswith("/filing_types/"):
            return answer(catalog)
        if url.endswith("/document_types"):
            return answer([{"code": "private", "name": "Confidential"}, {"code": "public", "name": "Public"}])
        if url.endswith("/filing_components"):
            return answer([{"code": "lead", "name": "Lead Document"}])
        return answer([])

    def post(url, **kwargs):
        assert url.endswith("/filings"), url
        submitted.append(kwargs["json"])
        return answer({"filing_id": "SYNTHETIC-303"})

    pdf = tmp_path / "waiver.pdf"
    pdf.write_bytes(
        pdf_bytes("Approved fee waiver order" if scenario == "application" else "Fee waiver application", pages=2)
    )
    config = tmp_path / "waiver-browser.json"
    config.write_text(
        json.dumps(
            {
                "baseUrl": live_server.url,
                "cookieName": settings.SESSION_COOKIE_NAME,
                "cookie": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "paymentUrl": reverse("payment", kwargs={"jurisdiction": "illinois"}) + f"?draft={filing.pk}",
                "scenario": scenario,
                "expectedName": catalog[-1]["name"],
                "expectedCodes": [item["code"] for item in reversed(catalog)],
                "waiverFile": str(pdf),
                "evidence": os.getenv("WAIVER_HIERARCHY_EVIDENCE_DIR", str(tmp_path / "evidence")),
            }
        )
    )
    with (
        patch("requests.get", side_effect=get),
        patch("requests.post", side_effect=post),
        patch("efile.views.waiver_documents.S3UploadHandler", return_value=handler),
        patch("efile.views.document_previews.S3UploadHandler", return_value=handler),
        patch("efile.utils.s3_upload_handler.S3UploadHandler", return_value=handler),
        patch("efile.views.payment.estimate_fees", return_value={}),
        patch("efile.views.review.get_case_questions", return_value=[]),
    ):
        result = subprocess.run(
            ["node", "tests/waiver-hierarchy-browser.js", str(config)],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    filing.refresh_from_db()
    assert filing.status == "submitted"
    assert len(submitted) == 1
    assert submitted[0]["tyler_payment_id"] == "wv-1"
    assert submitted[0]["al_court_bundle"][1]["filing_type"] == scenario
    document = filing.documents.get(role="supporting")
    assert document.filing_type_code == scenario
    assert filing.metadata_events.filter(path=f"documents.{document.pk}", kind="document_purpose").exists()
    assert document.preparation_reviewed_at is not None
