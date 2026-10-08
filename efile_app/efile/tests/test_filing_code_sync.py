"""Incremental imports preserve unchanged courts and roll back failed updates."""

from copy import deepcopy
from unittest.mock import patch

import pytest
import requests

from efile.services.filing_code_search import current_index, refresh_index, search_paths
from efile.services.filing_code_sync import export_entries

pytestmark = pytest.mark.django_db


def export(code="housing", name="Boston Housing Court", label="first"):
    return {
        "version": 1,
        "jurisdiction": "massachusetts",
        "court": {"code": code, "name": name, "revision": code + label},
        "categories": [{"code": "civil", "name": "Civil"}],
        "case_types": [
            {"code": "sp", "name": "Summary Process", "case_category": "civil", "initial": True},
            {"code": "debt", "name": "Debt collection", "case_category": "civil", "initial": False},
        ],
        "filing_types": [
            {"code": "complaint", "name": "Complaint", "case_category": "", "case_type": "", "timing": "Initial"},
            {"code": "answer", "name": "Answer", "case_category": "", "case_type": "", "timing": "Subsequent"},
            {
                "code": "motion",
                "name": "Motion to Dismiss",
                "case_category": None,
                "case_type": "sp",
                "timing": "Subsequent",
            },
        ],
    }


@pytest.fixture
def bulk(settings):
    settings.FILING_CODE_SYNC_MODE = "bulk"
    data = {
        "housing": export(),
        "district": export("district", "Boston District Court"),
    }
    with patch("efile.services.filing_code_sync.BulkCodeCatalog") as factory:
        catalog = factory.return_value
        catalog.jurisdiction = "massachusetts"
        catalog.manifest.side_effect = lambda: {code: deepcopy(item["court"]) for code, item in data.items()}
        catalog.court.side_effect = lambda court: deepcopy(data[court["code"]])
        yield data, catalog


def test_initial_import_and_unchanged_refresh_do_not_rewrite_paths(bulk):
    _, catalog = bulk
    assert refresh_index("massachusetts") == 6
    index = current_index("massachusetts")
    ids = list(index.paths.order_by("pk").values_list("pk", flat=True))
    assert search_paths(index, "eviction")["total"] == 2
    stamp = index.refreshed_at
    catalog.reset_mock()
    assert refresh_index("massachusetts") == 0
    assert catalog.manifest.call_count == 1
    catalog.court.assert_not_called()
    index.refresh_from_db()
    assert index.refreshed_at > stamp
    assert list(index.paths.order_by("pk").values_list("pk", flat=True)) == ids


def test_changed_court_only_and_retired_court_cleanup(bulk):
    data, catalog = bulk
    refresh_index("massachusetts")
    index = current_index("massachusetts")
    ids = set(index.paths.filter(court__code="district").values_list("pk", flat=True))
    data["housing"]["court"]["revision"] = "housing changed"
    data["housing"]["filing_types"][0]["name"] = "New complaint"
    catalog.reset_mock()
    assert refresh_index("massachusetts") == 3
    assert [call.args[0]["code"] for call in catalog.court.call_args_list] == ["housing"]
    assert set(index.paths.filter(court__code="district").values_list("pk", flat=True)) == ids
    assert index.paths.filter(filing_type__name="New complaint").exists()
    del data["housing"]
    assert refresh_index("massachusetts") == 0
    assert not index.paths.filter(court__code="housing").exists()
    index.refresh_from_db()
    assert set(index.court_snapshots) == {"district"}
    assert set(index.paths.values_list("pk", flat=True)) == ids


def test_failed_download_or_changed_manifest_preserves_entire_index(bulk):
    data, catalog = bulk
    refresh_index("massachusetts")
    index = current_index("massachusetts")
    ids = set(index.paths.values_list("pk", flat=True))
    data["housing"]["court"]["revision"] = "update"
    catalog.court.side_effect = requests.Timeout("unavailable")
    with pytest.raises(requests.Timeout):
        refresh_index("massachusetts")
    assert set(index.paths.values_list("pk", flat=True)) == ids
    catalog.court.side_effect = lambda court: deepcopy(data[court["code"]])
    manifest = {code: item["court"] for code, item in data.items()}
    catalog.manifest.side_effect = [manifest, {"housing": data["housing"]["court"]}]
    with pytest.raises(ValueError, match="changed during synchronization"):
        refresh_index("massachusetts")
    assert set(index.paths.values_list("pk", flat=True)) == ids
    # A removal-only refresh must also reject a manifest that changes mid-import.
    catalog.reset_mock()
    catalog.manifest.side_effect = [{"district": manifest["district"]}, manifest]
    with pytest.raises(ValueError, match="changed during synchronization"):
        refresh_index("massachusetts")
    catalog.court.assert_not_called()
    assert set(index.paths.values_list("pk", flat=True)) == ids


def test_database_failure_rolls_back_changes_and_deletions(bulk):
    data, _ = bulk
    refresh_index("massachusetts")
    index = current_index("massachusetts")
    ids = set(index.paths.values_list("pk", flat=True))
    del data["district"]
    data["housing"]["court"]["revision"] = "changed"
    data["housing"]["filing_types"][0]["name"] = "Changed"
    with patch("efile.services.filing_code_sync._insert_paths", side_effect=ValueError("insert failed")):
        with pytest.raises(ValueError, match="insert failed"):
            refresh_index("massachusetts")
    assert set(index.paths.values_list("pk", flat=True)) == ids
    index.refresh_from_db()
    assert set(index.court_snapshots) == {"housing", "district"}


def test_specific_filing_lists_override_generic_lists_and_timing_is_preserved():
    data = export()
    entries = list(export_entries(data, "massachusetts"))
    assert {(entry["case_type"]["code"], entry["filing_type"]["code"], entry["initial"]) for entry in entries} == {
        ("sp", "complaint", True),
        ("sp", "motion", False),
        ("debt", "answer", False),
    }
    data["filing_types"].append(
        {
            "code": "category",
            "name": "Category filing",
            "case_category": "civil",
            "case_type": "",
            "timing": "Both",
        }
    )
    entries = list(export_entries(data, "massachusetts"))
    assert not any(entry["filing_type"]["code"] in ("complaint", "answer") for entry in entries)
    assert len(entries) == 4


def test_subsequent_category_gate_matches_proxy_sql():
    data = export()
    data["case_types"] = [data["case_types"][0]]
    entries = list(export_entries(data, "massachusetts"))
    assert len(entries) == 1
    assert entries[0]["initial"] is True


def test_forced_court_redownloads_without_a_revision_change(bulk):
    _, catalog = bulk
    refresh_index("massachusetts")
    catalog.reset_mock()
    assert refresh_index("massachusetts", force=["housing"]) == 3
    assert [call.args[0]["code"] for call in catalog.court.call_args_list] == ["housing"]
    with pytest.raises(ValueError, match="nowhere"):
        refresh_index("massachusetts", force=["nowhere"])


def test_dry_run_reports_changes_without_saving(bulk):
    data, _ = bulk
    refresh_index("massachusetts")
    index = current_index("massachusetts")
    ids, snapshots = set(index.paths.values_list("pk", flat=True)), index.court_snapshots
    data["housing"]["court"]["revision"] = "changed"
    reports = []
    assert refresh_index("massachusetts", dry_run=True, progress=reports.append) == 3
    assert "Boston Housing Court (housing): 3 -> 3 paths" in reports
    index.refresh_from_db()
    assert index.court_snapshots == snapshots
    assert set(index.paths.values_list("pk", flat=True)) == ids


def test_court_emptied_by_a_partial_proxy_load_is_rejected_unless_forced(bulk):
    data, _ = bulk
    refresh_index("massachusetts")
    index = current_index("massachusetts")
    ids = set(index.paths.values_list("pk", flat=True))
    data["housing"]["court"]["revision"] = "half loaded"
    data["housing"]["filing_types"] = []
    with pytest.raises(ValueError, match="no filing paths"):
        refresh_index("massachusetts")
    assert set(index.paths.values_list("pk", flat=True)) == ids
    assert refresh_index("massachusetts", force=["housing"]) == 0
    assert not index.paths.filter(court__code="housing").exists()
