"""Exact provider names remain searchable when path-only aliases consume words."""

import pytest
from django.core.cache import cache, caches
from django.utils import timezone

from efile.models import FilingCodeIndex, FilingCodePath
from efile.services.filing_code_labels import LabelCounts
from efile.services.filing_code_search import indexed_path, search_grouped_paths, search_paths

pytestmark = pytest.mark.django_db


@pytest.fixture
def vermont_index():
    cache.clear()
    caches["shared"].clear()
    index = FilingCodeIndex.objects.create(
        jurisdiction="vermont",
        source_url="https://efile-test.suffolklitlab.org",
        refreshed_at=timezone.now(),
        rules_digest="test",
        vocabulary={"words": [], "tokens": [], "courts": {"sc:addison": "Addison Unit"}},
        court_snapshots={},
    )
    specs = [
        ("Probate", "Probate estate", "Application to Waive Filing and Service Fees", "60000228", True),
        ("Civil", "Small Claims $1,000 or less", "Application to Waive Filing and Service Fees", "60000228", True),
        ("Civil", "Small Claims $1,000 or less", "Answer", "7631", False),
        ("Civil", "Small Claims $1,000 or less", "Small Claims Answer", "named-answer", False),
    ]
    entries = []
    for category, case_type, filing, filing_code, initial in specs:
        path = {
            "court": {"code": "sc:addison", "name": "Addison Unit"},
            "case_category": {"code": category.lower(), "name": category},
            "case_type": {"code": case_type.lower().replace(" ", "-"), "name": case_type},
            "filing_type": {"code": filing_code, "name": filing},
        }
        entries.append(indexed_path("vermont", path, initial))
    FilingCodePath.objects.bulk_create([FilingCodePath(index=index, **entry) for entry in entries])
    labels = LabelCounts()
    for entry in entries:
        labels.add(entry)
    labels.save(index)
    index.labels_built_at = timezone.now()
    index.save(update_fields=["labels_built_at"])
    return index


def _rows(response):
    return {(row["case_category"]["name"], row["filing_type"]["name"]) for row in response["results"]}


def test_exact_fee_waiver_label_survives_outside_alias_scope(vermont_index):
    exact = "Application to Waive Filing and Service Fees"
    path_rows = _rows(search_paths(vermont_index, exact, initial=True))
    assert ("Probate", exact) in path_rows
    assert ("Civil", exact) in path_rows

    id_rows = _rows(search_paths(vermont_index, "600-00228", initial=True))
    assert id_rows == {("Civil", exact)}

    groups = search_grouped_paths(vermont_index, exact, initial=True)["groups"]
    fee_group = next(group for group in groups if group["name"] == exact)
    assert fee_group["path_count"] == 2
    id_groups = search_grouped_paths(vermont_index, "600-00228", initial=True)["groups"]
    id_group = next(group for group in id_groups if group["name"] == exact)
    assert id_group["path_count"] == 1


@pytest.mark.parametrize("strong_only", [False, True])
def test_exact_small_claims_answer_title_and_answer_alias_are_both_searchable(vermont_index, strong_only):
    exact_rows = _rows(search_paths(vermont_index, "Small Claims Answer", initial=False))
    assert ("Civil", "Small Claims Answer") in exact_rows
    assert ("Civil", "Answer") in exact_rows

    answer_rows = _rows(search_paths(vermont_index, "Answer", initial=False))
    assert ("Civil", "Answer") in answer_rows

    id_rows = _rows(search_paths(vermont_index, "100-00126", initial=False))
    assert id_rows == {("Civil", "Answer")}

    groups = search_grouped_paths(vermont_index, "Small Claims Answer", initial=False, strong_only=strong_only)[
        "groups"
    ]
    assert {group["name"] for group in groups} == {"Answer", "Small Claims Answer"}
    answer_group = next(group for group in groups if group["name"] == "Answer")
    assert answer_group["path_count"] >= 1

    labels_built = sorted((group["name"], group["path_count"]) for group in groups)
    vermont_index.labels_built_at = None
    vermont_index.save(update_fields=["labels_built_at"])
    cache.clear()
    caches["shared"].clear()
    ungrouped_labels = search_grouped_paths(
        vermont_index, "Small Claims Answer", initial=False, strong_only=strong_only
    )["groups"]
    assert sorted((group["name"], group["path_count"]) for group in ungrouped_labels) == labels_built
