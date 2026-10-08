"""Copying codes from the EFSP database, indexing the copy, scheduling, and staff requests."""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from efile.management.commands.refresh_filing_code_index import next_daily_run
from efile.models import FilingCodeCourtCatalog, FilingCodeJob, StaffAudit
from efile.services import filing_code_copy
from efile.services.filing_code_copy import EfspCodesDatabase, copy_codes, rebuild, resync, run_jobs
from efile.services.filing_code_search import current_index, search_grouped_paths
from efile.tests.test_staff_tools import verified_client

pytestmark = pytest.mark.django_db


def court_export(code, name, filings=("Complaint", "Answer")):
    return {
        "court": {"code": code, "name": name, "revision": f"{code}-{len(filings)}"},
        "categories": [{"code": "civ", "name": "Civil"}],
        "case_types": [{"code": "ct", "name": "Eviction", "case_category": "civ", "initial": True}],
        "filing_types": [
            {"code": f"f{i}", "name": filing, "case_category": "civ", "case_type": "", "timing": "Both"}
            for i, filing in enumerate(filings)
        ],
    }


class FakeEfsp:
    """Stands in for the EFSP database: courts by code, and which ones were read."""

    def __init__(self, *exports):
        self.exports = {export["court"]["code"]: export for export in exports}
        self.read = []

    @contextmanager
    def __call__(self, jurisdiction):
        source = MagicMock()
        source.manifest.side_effect = lambda: {code: export["court"] for code, export in self.exports.items()}
        source.court.side_effect = lambda court: self.read.append(court["code"]) or self.exports[court["code"]]
        yield source


@pytest.fixture
def efsp():
    fake = FakeEfsp(court_export("adams", "Adams County"), court_export("cook:cvd1", "Cook County"))
    with patch.object(filing_code_copy, "EfspCodesDatabase", fake):
        yield fake


def test_copy_reads_only_changed_courts_and_drops_removed_ones(efsp):
    assert copy_codes("illinois") == {"courts": 2, "changed": 2, "removed": 0}
    assert copy_codes("illinois")["changed"] == 0
    efsp.exports["adams"] = court_export("adams", "Adams County", ("Complaint", "Answer", "Motion"))
    del efsp.exports["cook:cvd1"]
    efsp.read.clear()
    assert copy_codes("illinois") == {"courts": 1, "changed": 1, "removed": 1}
    assert efsp.read == ["adams"]
    assert list(FilingCodeCourtCatalog.objects.values_list("code", "filing_count")) == [("adams", 3)]


def test_a_court_that_suddenly_has_no_filings_keeps_its_old_copy(efsp):
    copy_codes("illinois")
    efsp.exports["adams"] = court_export("adams", "Adams County", ())
    with pytest.raises(ValueError, match="no filing types"):
        copy_codes("illinois")
    assert FilingCodeCourtCatalog.objects.get(code="adams").filing_count == 2
    copy_codes("illinois", force=["adams"])
    assert FilingCodeCourtCatalog.objects.get(code="adams").filing_count == 0


def test_dry_run_reads_and_reports_without_saving(efsp):
    assert copy_codes("illinois", dry_run=True)["changed"] == 2
    assert not FilingCodeCourtCatalog.objects.exists()


def test_resync_indexes_the_copy_and_rebuild_needs_no_efsp(efsp):
    assert resync("illinois") > 0
    index = current_index("illinois")
    assert search_grouped_paths(index, "complaint")["total"] == 1
    assert index.vocabulary["courts"] == {"adams": "Adams County", "cook:cvd1": "Cook County"}
    indexed = sum(item["count"] for item in index.court_snapshots.values())
    with patch.object(filing_code_copy, "EfspCodesDatabase", side_effect=AssertionError("contacted the EFSP")):
        assert rebuild("illinois") == indexed
    assert search_grouped_paths(current_index("illinois"), "answer")["total"] == 1


def test_rebuild_without_a_copy_says_to_resync_first():
    with pytest.raises(ValueError, match="Resync codes first"):
        rebuild("illinois")


def test_the_efsp_connection_must_be_read_only(settings):
    settings.EFSP_CODES_DATABASE_URL = "postgresql://reader@efsp.example/postgres"
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = {"transaction_read_only": "off"}
    with patch("psycopg.connect", return_value=connection), pytest.raises(ValueError, match="not read only"):
        with EfspCodesDatabase("illinois"):
            pass
    assert connection.read_only is True
    connection.close.assert_called_once()
    settings.EFSP_CODES_DATABASE_URL = ""
    with pytest.raises(ValueError, match="EFSP_CODES_DATABASE_URL"):
        EfspCodesDatabase("illinois")


def test_an_incomplete_efsp_update_copies_nothing(settings):
    settings.EFSP_CODES_DATABASE_URL = "postgresql://reader@efsp.example/postgres"
    source = EfspCodesDatabase("illinois")
    rows = [{"code": "adams", "name": "Adams County", "fileable": True, "versions": 2, "revision": "r"}]
    with patch.object(EfspCodesDatabase, "_rows", return_value=rows), pytest.raises(ValueError, match="Incomplete"):
        source.manifest()
    # Tyler's internal "System" row is fileable but has no code lists; it is skipped, not fatal.
    rows = [
        {"code": "0", "name": "System", "fileable": True, "versions": 0, "revision": "s"},
        {
            "code": "cook:dv",
            "name": "Cook County - Domestic Violence",
            "fileable": False,
            "versions": 2,
            "revision": "d",
        },
        {"code": "adams", "name": "Adams County", "fileable": True, "versions": 3, "revision": "a"},
    ]
    with patch.object(EfspCodesDatabase, "_rows", return_value=rows):
        assert list(source.manifest()) == ["adams"]


def test_queued_jobs_run_once_and_record_the_outcome(efsp):
    resync_job = FilingCodeJob.objects.create(kind="resync", jurisdiction="illinois")
    rebuild_job = FilingCodeJob.objects.create(kind="rebuild", jurisdiction="vermont")
    run_jobs(["illinois", "vermont"], log=lambda line: None)
    resync_job.refresh_from_db()
    rebuild_job.refresh_from_db()
    assert resync_job.status == "succeeded" and "illinois:" in resync_job.message
    assert rebuild_job.status == "failed" and "Resync codes first" in rebuild_job.message
    assert resync_job.started_at and resync_job.finished_at


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 6, 20, 0, tzinfo=UTC), "2026-10-06 21:30 EDT"),  # 16:00 Eastern: tonight
        (datetime(2026, 10, 7, 2, 0, tzinfo=UTC), "2026-10-07 21:30 EDT"),  # 22:00 Eastern: tomorrow
        (datetime(2026, 11, 1, 3, 0, tzinfo=UTC), "2026-11-01 21:30 EST"),  # across the DST change
    ],
)
def test_daily_runs_land_at_the_configured_eastern_time(now, expected):
    assert f"{next_daily_run(now, '21:30', 'America/New_York'):%Y-%m-%d %H:%M %Z}" == expected


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_user(
        username="root", password="a-strong-local-password", is_staff=True, is_superuser=True
    )


def test_staff_can_queue_a_resync_or_rebuild_once(client, superuser):
    client = verified_client(client, superuser)
    url = reverse("litefile_staff:filing_codes")
    page = client.get(url)
    assert page.status_code == 200
    assert b"Resync codes" in page.content and b"Rebuild code search indexes" in page.content
    client.post(url, {"kind": "resync", "jurisdiction": "illinois"})
    client.post(url, {"kind": "resync", "jurisdiction": "illinois"})
    client.post(url, {"kind": "rebuild", "jurisdiction": ""})
    assert list(FilingCodeJob.objects.order_by("pk").values_list("kind", "jurisdiction", "status")) == [
        ("resync", "illinois", "queued"),
        ("rebuild", "", "queued"),
    ]
    assert StaffAudit.objects.filter(action="filing_codes_resync", jurisdiction="illinois").count() == 1
    client.post(url, {"kind": "drop tables", "jurisdiction": "illinois"})
    assert FilingCodeJob.objects.count() == 2


def test_only_superusers_reach_the_filing_codes_page(client, django_user_model):
    from efile.models import StaffRoleGrant

    staff = django_user_model.objects.create_user(username="staff", password="a-strong-local-password", is_staff=True)
    StaffRoleGrant.objects.create(user=staff, jurisdiction="illinois", role="accounts")
    client = verified_client(client, staff)
    assert client.get(reverse("litefile_staff:filing_codes")).status_code == 403
    assert client.post(reverse("litefile_staff:filing_codes"), {"kind": "resync"}).status_code == 403
    assert not FilingCodeJob.objects.exists()


@pytest.fixture(autouse=True)
def court_eligibility():
    with patch("efile.services.filing_code_search.eligible_court_codes", return_value=["adams", "cook:cvd1"]):
        yield
