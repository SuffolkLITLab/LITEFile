"""Exercise interleavings between obsolete workers, requeues, and recovery."""

import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from efile.models import DocumentExtraction, FilingDocument, FilingDraft
from efile.services.document_extractions import (
    claim_next_extraction,
    process_document_extraction,
    queue_document_extraction,
    record_extraction_failure,
    renew_extraction_lease,
)
from efile.tests.helpers import reviewed_document


@pytest.fixture
def lead(db, django_user_model):
    user = django_user_model.objects.create_user(username="claim-test")
    draft = FilingDraft.objects.create(user=user, jurisdiction="illinois")
    return reviewed_document(draft=draft, role=FilingDocument.Role.LEAD, name="lead.pdf", s3_key="lead.pdf")


def expire(job):
    DocumentExtraction.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))


@contextmanager
def fake_pdf(*args):
    yield "unused.pdf", 1, 1


@pytest.mark.parametrize("replacement", ["requeue", "recover"])
def test_old_result_cannot_overwrite_new_attempt(lead, replacement):
    queue_document_extraction(lead)
    old = claim_next_extraction()
    new = None

    def analyze(*args, **kwargs):
        nonlocal new
        if replacement == "requeue":
            queue_document_extraction(lead)
        else:
            expire(old)
        new = claim_next_extraction()
        return {"document title": "obsolete result"}

    with (
        patch(
            "efile.services.document_extractions.S3UploadHandler",
            return_value=Mock(download_file=Mock(return_value={"success": True})),
        ),
        patch("efile.services.document_extractions.limited_pdf", fake_pdf),
        patch("efile.services.document_extractions.analyze_document", side_effect=analyze),
    ):
        assert process_document_extraction(old.pk, old.claim_token) is None
    current = DocumentExtraction.objects.get(pk=old.pk)
    assert new is not None
    assert current.claim_token == new.claim_token != old.claim_token
    assert current.status == DocumentExtraction.Status.PROCESSING
    lead.draft.refresh_from_db()
    assert lead.draft.extracted_guesses == {}
    assert record_extraction_failure(old.pk, old.claim_token, "obsolete error") is None
    assert not renew_extraction_lease(old.pk, old.claim_token)


def test_requeue_before_download_prevents_processing(lead):
    queue_document_extraction(lead)
    old = claim_next_extraction()
    queue_document_extraction(lead)
    with patch("efile.services.document_extractions.S3UploadHandler") as handler:
        assert process_document_extraction(old.pk, old.claim_token) is None
    handler.assert_not_called()


def test_requeue_during_download_prevents_outbound_analysis(lead):
    queue_document_extraction(lead)
    old = claim_next_extraction()

    def download(*args):
        lead.draft.ai_assistance_opted_out = True
        lead.draft.save()
        queue_document_extraction(lead)
        return {"success": True}

    with (
        patch("efile.services.document_extractions.S3UploadHandler", return_value=Mock(download_file=download)),
        patch("efile.services.document_extractions.limited_pdf", fake_pdf),
        patch("efile.services.document_extractions.analyze_document") as analyze,
    ):
        assert process_document_extraction(old.pk, old.claim_token) is None
    analyze.assert_not_called()


@pytest.mark.parametrize("requeue", [True, False])
def test_preference_change_during_local_conversion_stops_model_request(lead, requeue):
    queue_document_extraction(lead)
    job = claim_next_extraction()

    def convert(*args):
        lead.draft.ai_assistance_opted_out = True
        lead.draft.save()
        if requeue:
            queue_document_extraction(lead)
        return "local text", 1

    with (
        patch(
            "efile.services.document_extractions.S3UploadHandler",
            return_value=Mock(download_file=Mock(return_value={"success": True})),
        ),
        patch("efile.services.document_extractions.limited_pdf", fake_pdf),
        patch("efile.services.document_extractions._source_text", side_effect=convert),
        patch("efile.services.document_extractions._form_identifier_pass", return_value=({}, "pypdf", 0, "")),
        patch("efile.services.document_extractions.get_default_model", return_value="test-model"),
        patch("efile.services.document_extractions.extract_fields_from_file") as extract,
    ):
        assert process_document_extraction(job.pk, job.claim_token) is None
    extract.assert_not_called()
    assert record_extraction_failure(job.pk, job.claim_token, "Worker exited") is None
    job.refresh_from_db()
    assert job.status == DocumentExtraction.Status.PENDING
    assert job.attempts == 0
    assert job.error == ""
    assert claim_next_extraction() is not None


@pytest.mark.parametrize("attempts_before", [0, 2])
@pytest.mark.parametrize("initial_opted_out", [True, False])
@override_settings(DOCUMENT_EXTRACTION_MAX_ATTEMPTS=3)
def test_preference_change_at_completion_refunds_only_obsolete_attempt(lead, attempts_before, initial_opted_out):
    FilingDraft.objects.filter(pk=lead.draft_id).update(ai_assistance_opted_out=initial_opted_out)
    job = queue_document_extraction(lead)
    DocumentExtraction.objects.filter(pk=job.pk).update(attempts=attempts_before)
    claimed = claim_next_extraction()

    def analyze(*args, **kwargs):
        # Simulate an update that does not use the normal requeue endpoint.
        FilingDraft.objects.filter(pk=lead.draft_id).update(ai_assistance_opted_out=not initial_opted_out)
        return {"document title": "obsolete result"}

    with (
        patch(
            "efile.services.document_extractions.S3UploadHandler",
            return_value=Mock(download_file=Mock(return_value={"success": True})),
        ),
        patch("efile.services.document_extractions.limited_pdf", fake_pdf),
        patch("efile.services.document_extractions.analyze_document", side_effect=analyze),
    ):
        assert process_document_extraction(job.pk, claimed.claim_token) is None
    # The supervisor must treat the child's normal exit as a no-op.
    assert record_extraction_failure(job.pk, claimed.claim_token, "Worker exited") is None
    job.refresh_from_db()
    assert job.status == DocumentExtraction.Status.PENDING
    assert job.attempts == attempts_before
    assert job.claim_token is None
    assert job.lease_expires_at is None
    assert job.error == ""
    lead.draft.refresh_from_db()
    assert lead.draft.extracted_guesses == {}
    new_claim = claim_next_extraction()
    assert new_claim is not None
    assert new_claim.attempts == attempts_before + 1
    assert new_claim.claim_token != claimed.claim_token


@override_settings(DOCUMENT_EXTRACTION_MAX_ATTEMPTS=1)
def test_interrupted_final_attempt_becomes_terminal(lead):
    queue_document_extraction(lead)
    job = claim_next_extraction()
    expire(job)
    assert claim_next_extraction() is None
    job.refresh_from_db()
    assert job.status == DocumentExtraction.Status.FAILED
    assert job.completed_at is not None
    assert job.claim_token is None


@override_settings(DOCUMENT_EXTRACTION_MAX_ATTEMPTS=2)
def test_failure_backs_off_and_does_not_store_exception_contents(lead):
    queue_document_extraction(lead)
    job = claim_next_extraction()
    record_extraction_failure(job.pk, job.claim_token, "secret-token-and-filing-body")
    job.refresh_from_db()
    assert "secret" not in job.error
    assert job.status == DocumentExtraction.Status.PENDING
    assert claim_next_extraction() is None
    DocumentExtraction.objects.filter(pk=job.pk).update(available_at=timezone.now() - timedelta(seconds=1))
    retry = claim_next_extraction()
    assert retry.attempts == 2
    assert retry.claim_token != job.claim_token


def test_heartbeat_extends_only_live_claims(lead):
    queue_document_extraction(lead)
    job = claim_next_extraction()
    assert renew_extraction_lease(job.pk, job.claim_token)
    expire(job)
    assert not renew_extraction_lease(job.pk, job.claim_token)


@override_settings(DOCUMENT_EXTRACTION_TIMEOUT_SECONDS=1)
def test_supervisor_terminates_a_timed_out_child_and_requeues(lead):
    from django.core.management import call_command

    queue_document_extraction(lead)
    child = Mock()
    child.is_alive.side_effect = [True, True, False]
    with (
        patch(
            "efile.management.commands.process_document_extractions.multiprocessing.get_context",
            return_value=Mock(Process=Mock(return_value=child)),
        ),
        patch("efile.management.commands.process_document_extractions.time.monotonic", side_effect=[0, 2, 2]),
    ):
        call_command("process_document_extractions", once=True)
    child.terminate.assert_called_once()
    job = DocumentExtraction.objects.get(document=lead)
    assert job.status == DocumentExtraction.Status.PENDING
    assert job.claim_token is None


def test_real_spawned_worker_can_start_and_record_failure(tmp_path):
    """Use an isolated migrated database, visible to the spawned process."""
    code = """
import django
django.setup()
from django.core.management import call_command
from efile.models import DocumentExtraction, FilingDocument, FilingDraft, UserProfile
from efile.services.document_extractions import queue_document_extraction
call_command('migrate', verbosity=0)
user = UserProfile.objects.create_user(username='worker-smoke')
draft = FilingDraft.objects.create(user=user, jurisdiction='illinois')
document = FilingDocument.objects.create(draft=draft, role='lead', name='lead.pdf', s3_key='lead.pdf')
job = queue_document_extraction(document)
call_command('process_document_extractions', once=True)
job.refresh_from_db()
assert job.status == DocumentExtraction.Status.PENDING
assert job.attempts == 1
assert job.claim_token is None
assert job.available_at > job.started_at
"""
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "efile.settings_dev",
        "FLY_APP_NAME": "",
        "EFSP_TEST_DOCUMENT_URL": "",
        "DJANGO_SECRET_KEY": "isolated-worker-smoke-test-key",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'worker.sqlite3'}",
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "DOCUMENT_EXTRACTION_TIMEOUT_SECONDS": "30",
    }
    result = subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    # Proves the child reached processing, rather than silently failing to
    # import, exhausting its memory budget, or timing out during startup.
    assert "failed (RuntimeError)" in result.stderr
    assert "AWS credentials not fully configured" in result.stderr
