"""Regression coverage for searchable filing ownership and response backfill."""

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from efile.models import FilingDraft, FilingIdentifier
from efile.services.handoff import local_submission
from efile.tests.test_filing_history import accepted_detail, rejected_detail
from efile.tests.test_submission_tracker import sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="indexed-owner", tyler_jurisdiction="illinois")


def make_draft(owner, **kwargs):
    return FilingDraft.objects.create(
        user=owner, jurisdiction="illinois", court_code="kane", status=FilingDraft.Status.SUBMITTED, **kwargs
    )


def test_response_index_tracks_distinct_ids_updates_and_deletion(owner):
    draft = make_draft(
        owner,
        submission_response={
            "filing_ids": ["one", "one", "two"],
            "envelope_id": "not-a-filing",
            "nested": {"identificationCategory": {"value": "FILINGID"}, "identificationID": {"value": "three"}},
        },
    )
    assert set(draft.filing_identifiers.values_list("filing_id", flat=True)) == {"one", "two", "three"}
    assert local_submission(owner, "illinois", "kane", "two") == draft
    assert local_submission(owner, "illinois", "other-court", "two") is None
    draft.submission_response = {"filingId": "replacement"}
    draft.save(update_fields=["submission_response"])
    assert list(draft.filing_identifiers.values_list("filing_id", flat=True)) == ["replacement"]
    assert local_submission(owner, "illinois", "kane", "two") is None
    draft.submission_response = {"filingId": "not-saved"}
    draft.save(update_fields=["updated_at"])
    assert list(draft.filing_identifiers.values_list("filing_id", flat=True)) == ["replacement"]
    draft.mark_error({"filing_id": "ambiguous-filing"})
    assert list(draft.filing_identifiers.values_list("filing_id", flat=True)) == ["ambiguous-filing"]
    assert local_submission(owner, "illinois", "kane", "ambiguous-filing") is None
    draft.delete()
    assert not FilingIdentifier.objects.exists()


def test_backfill_indexes_historical_response_shapes_without_envelope_ids(owner):
    draft = make_draft(
        owner,
        submission_response={
            "filingID": "old-one",
            "filingIds": ["old-two", "old-two"],
            "envelope_id": "envelope-only",
            "nested": [{"filing_id": "old-three"}],
        },
    )
    FilingIdentifier.objects.all().delete()
    migration = import_module("efile.migrations.0044_filing_identifiers")
    backfill = vars(migration)["backfill_filing_identifiers"]
    apps = MigrationExecutor(connection).loader.project_state([("efile", "0044_filing_identifiers")]).apps
    backfill(apps, SimpleNamespace(connection=connection))
    backfill(apps, SimpleNamespace(connection=connection))
    assert set(draft.filing_identifiers.values_list("filing_id", flat=True)) == {"old-one", "old-two", "old-three"}


@pytest.mark.parametrize("status", ["REJECTED", "Returned", "  rejected  ", " RETURNED ", "failed", "accepted"])
def test_correction_link_uses_normalized_return_status(client, owner, status):
    draft = make_draft(owner, submission_response={"filing_id": "returned-id"})
    sign_in(client, owner)
    payload = rejected_detail()
    payload["filingStatus"]["filingStatusCode"] = status
    with (
        patch("efile.views.my_cases.fetch_filing_detail", return_value=payload),
        patch("efile.views.my_cases.court_names", return_value={}),
    ):
        response = client.get(reverse("filing_detail", args=["illinois", "kane", "returned-id"]))
    assert response.status_code == 200
    link = reverse("correct_filing", args=[draft.pk])
    assert (link in response.content.decode()) == (status.strip().lower() in {"rejected", "returned"})


def test_remote_only_detail_does_not_load_other_accounts_drafts(client, owner, django_user_model):
    other = django_user_model.objects.create_user(username="other-indexed-owner", tyler_jurisdiction="illinois")
    unrelated_ids = {
        make_draft(
            other, submission_response={"filing_id": f"other-{i}"}, submission_snapshot={"large": "x" * 10000}
        ).pk
        for i in range(20)
    }
    sign_in(client, owner)
    original = FilingDraft.from_db

    def check_loaded(db, field_names, values):
        instance = original(db, field_names, values)
        assert instance.pk not in unrelated_ids, "Detail lookup materialized another account's draft"
        return instance

    with (
        patch.object(FilingDraft, "from_db", side_effect=check_loaded),
        patch("efile.views.my_cases.fetch_filing_detail", return_value=accepted_detail()) as fetch,
        patch("efile.views.my_cases.court_names", return_value={}),
    ):
        response = client.get(reverse("filing_detail", args=["illinois", "kane", "remote-only"]))
    assert response.status_code == 200
    fetch.assert_called_once()


def test_saves_that_leave_the_response_alone_skip_the_index(owner):
    draft = make_draft(owner, submission_response={"filing_id": "kept"})
    draft = FilingDraft.objects.get(pk=draft.pk)
    draft.case_title = "Renamed"
    with CaptureQueriesContext(connection) as queries:
        draft.save()
    assert not [query for query in queries if "efile_filingidentifier" in query["sql"]]
    draft.submission_response["filing_id"] = "changed-in-place"
    draft.save()
    assert list(draft.filing_identifiers.values_list("filing_id", flat=True)) == ["changed-in-place"]


def test_indexing_an_id_another_save_already_indexed_is_not_an_error(owner):
    draft = make_draft(owner, submission_response={"filing_id": "raced"})
    stale = FilingDraft.objects.get(pk=draft.pk)
    stale._indexed_filing_ids = set()
    stale.save()
    assert list(draft.filing_identifiers.values_list("filing_id", flat=True)) == ["raced"]
