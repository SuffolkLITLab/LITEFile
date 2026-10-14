"""The model can refine searches, but cannot escape live court/stage constraints."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
from django.db import OperationalError
from django.db import connection as db_connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from efile.models import FilingCodeIndex, FilingCodePath
from efile.services.classification_search import search_classification_candidates
from efile.services.filing_code_search import indexed_path, rules, source_url
from efile.services.taxonomy_classification import HierarchicalDocumentClassifier
from efile.tests.test_taxonomy_classification import FakeTaxonomy


def selected(code, name="Name"):
    return {"status": "selected", "route_key": code, "name": name}


@pytest.fixture
def search_args():
    return dict(
        jurisdiction="vermont",
        query="answer",
        level="filing type",
        filing_phase="subsequent",
        selections={"court": selected("county"), "case category": selected("civil"), "case type": selected("small")},
        references={"C001": {"route_key": "answer", "name": "Answer"}},
        source_url=source_url(),
    )


def run_search(args):
    return search_classification_candidates(
        jurisdiction=args["jurisdiction"],
        query=args["query"],
        level=args["level"],
        filing_phase=args["filing_phase"],
        selections=args["selections"],
        references=args["references"],
        source_url=args["source_url"],
    )


@pytest.fixture
def index(db):
    index = FilingCodeIndex.objects.create(
        jurisdiction="vermont",
        source_url=source_url(),
        rules_digest=rules()[1],
        refreshed_at=timezone.now(),
        vocabulary={"words": ["answer"], "tokens": ["answer"], "courts": []},
    )
    path = {
        "court": {"code": "county", "name": "County Unit"},
        "case_category": {"code": "civil", "name": "Civil"},
        "case_type": {"code": "small", "name": "Small Claims $1,000 or less"},
        "filing_type": {"code": "answer", "name": "Answer"},
    }
    FilingCodePath.objects.create(index=index, **indexed_path("vermont", path, False))
    for facet in ("court", "case_category", "case_type"):
        other = deepcopy(path)
        other[facet]["code"] = "other"
        other[facet]["name"] = "Other"
        FilingCodePath.objects.create(index=index, **indexed_path("vermont", other, False))
    FilingCodePath.objects.create(index=index, **indexed_path("vermont", path, True))
    stale = deepcopy(path)
    stale["filing_type"] = {"code": "removed", "name": "Answer removed"}
    FilingCodePath.objects.create(index=index, **indexed_path("vermont", stale, False))
    return index


def test_search_uses_real_index_and_filters_court_stage_parents_and_stale_codes(index, search_args):
    result = run_search(search_args)
    assert result["status"] == "ok"
    assert len(result["results"]) == 1
    assert result["results"][0]["selection_ref"] == "C001"
    assert result["results"][0]["case_type"] == "Small Claims $1,000 or less"
    assert result["index_refreshed_at"] == index.refreshed_at.isoformat()


def test_search_rejects_renamed_live_codes(index, search_args):
    search_args["references"]["C001"]["name"] = "New label"
    assert run_search(search_args)["results"] == []


def test_search_skips_count_and_display_only_details(index, search_args):
    with (
        CaptureQueriesContext(db_connection) as queries,
        patch("efile.services.filing_code_search.serialize_path", side_effect=AssertionError("full serializer")),
    ):
        assert run_search(search_args)["results"]
    assert not any("COUNT(" in query["sql"].upper() for query in queries)


def test_duplicate_parent_paths_do_not_crowd_out_alternatives(index, search_args):
    original = index.paths.first()
    row = {facet: getattr(original, facet) for facet in ("court", "case_category", "case_type", "filing_type")}
    for _ in range(12):
        FilingCodePath.objects.create(index=index, **indexed_path("vermont", row, False))
    row["case_category"] = {"code": "second", "name": "Second category"}
    row["case_type"] = {"code": "last", "name": "ZZZ claims"}
    FilingCodePath.objects.create(index=index, **indexed_path("vermont", row, False))
    search_args.update(
        level="case category",
        selections={"court": selected("county")},
        references={
            "C001": {"route_key": "civil", "name": "Civil"},
            "C002": {"route_key": "second", "name": "Second category"},
        },
    )
    result = run_search(search_args)
    assert [row["selection_ref"] for row in result["results"]] == ["C001", "C002"]


@pytest.mark.django_db
@pytest.mark.parametrize("previous,limit", [("10000", "2000"), ("100", "100"), ("0", "2000")])
def test_postgres_search_timeout_restores_previous_setting(search_args, previous, limit):
    connection = MagicMock(vendor="postgresql")
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (previous,)
    with (
        patch("efile.services.classification_search.connection", connection),
        patch("efile.services.classification_search.current_index", return_value=None),
    ):
        assert run_search(search_args)["status"] == "unavailable"
    calls = cursor.execute.call_args_list
    assert calls[1].args[1] == [limit]
    assert calls[-1].args[1] == [previous]


def test_unavailable_filings_are_not_suggested(index, search_args):
    with patch("efile.services.filing_code_search.filing_unavailable_message", return_value="Unavailable"):
        assert run_search(search_args)["results"] == []


@pytest.mark.parametrize("change", ["missing", "provider", "rules"])
def test_incompatible_index_is_not_used(index, search_args, change):
    if change == "missing":
        index.delete()
    else:
        if change == "provider":
            index.source_url = "https://other.example"
        else:
            index.rules_digest = "old"
        index.save()
    assert run_search(search_args)["status"] == "unavailable"


@pytest.mark.parametrize("field,value", [("filing_phase", "unknown"), ("level", "court")])
def test_unsafe_scope_never_queries_index(search_args, field, value):
    search_args[field] = value
    with patch("efile.services.classification_search.current_index") as lookup:
        assert run_search(search_args)["status"] == "unavailable"
    lookup.assert_not_called()


@pytest.mark.django_db
def test_database_failure_is_an_unavailable_tool(search_args):
    with patch("efile.services.classification_search.current_index", side_effect=OperationalError):
        assert run_search(search_args)["status"] == "unavailable"


def classify_with_search(replies, lookup):
    classifier = HierarchicalDocumentClassifier(taxonomy=FakeTaxonomy(), model="test-model")
    with (
        patch("efile.services.taxonomy_classification.chat_completion", side_effect=replies) as chat,
        patch("efile.services.taxonomy_classification.search_classification_candidates", return_value=lookup) as search,
    ):
        result = classifier._select(
            level="filing type",
            jurisdiction="massachusetts",
            candidates=[{"route_key": "live-code", "name": "Complaint"}],
            evidence={},
            source_text="Complaint for divorce",
            filing_phase="initial",
            selections={"court": selected("court")},
            crosswalk=[],
            crosswalk_summary={},
        )
    return result, chat, search


def test_model_can_refine_query_then_select_only_a_live_reference():
    result, chat, search = classify_with_search(
        [
            {"status": "request_more_candidates", "search_query": "divorce"},
            {"status": "request_more_candidates", "search_query": "complaint divorce"},
            {"status": "selected", "selection_ref": "C001", "confidence": 0.9},
        ],
        {"status": "ok", "results": [{"selection_ref": "C001", "filing_type": "Complaint"}]},
    )
    assert result["route_key"] == "live-code"
    assert result["search_rounds"] == 2
    assert [call.kwargs["query"] for call in search.call_args_list] == ["divorce", "complaint divorce"]
    assert chat.call_count == 3
    assert "Filing-code search result" in chat.call_args.kwargs["messages"][-1]["content"]


@pytest.mark.parametrize("query", [None, [], {}, "", " ", "a" * 201])
def test_invalid_tool_arguments_abstain_without_search(query):
    result, chat, search = classify_with_search([{"status": "request_more_candidates", "search_query": query}], {})
    assert result["status"] == "abstain"
    assert chat.call_count == 1
    search.assert_not_called()


@pytest.mark.parametrize("queries", [["answer", " ANSWER "], ["one", "two", "three"]])
def test_repeated_queries_and_round_limit_stop_the_loop(queries):
    result, chat, search = classify_with_search(
        [{"status": "request_more_candidates", "search_query": query} for query in queries],
        {"status": "ok", "results": []},
    )
    assert result["status"] == "abstain"
    assert search.call_count == len(queries) - 1
    assert chat.call_count == len(queries)


def test_unavailable_search_stops_without_guessing():
    result, chat, search = classify_with_search(
        [{"status": "request_more_candidates", "search_query": "complaint"}],
        {"status": "unavailable", "reason": "No index", "results": []},
    )
    assert result["status"] == "abstain"
    assert chat.call_count == search.call_count == 1


def test_search_does_not_authorize_invented_references():
    result, _, _ = classify_with_search(
        [
            {"status": "request_more_candidates", "search_query": "complaint"},
            {"status": "selected", "selection_ref": "C999", "confidence": 1},
        ],
        {"status": "ok", "results": []},
    )
    assert result["status"] == "abstain"
    assert "route_key" not in result


def test_full_classifier_passes_selected_parent_codes_to_search():
    classifier = HierarchicalDocumentClassifier(taxonomy=FakeTaxonomy(), model="test-model")
    choose = {"status": "selected", "selection_ref": "C001", "confidence": 0.9}
    with (
        patch(
            "efile.services.taxonomy_classification.chat_completion",
            side_effect=[
                choose,
                choose,
                choose,
                {"status": "request_more_candidates", "search_query": "divorce"},
                choose,
            ],
        ),
        patch(
            "efile.services.taxonomy_classification.search_classification_candidates",
            return_value={"status": "ok", "results": []},
        ) as search,
    ):
        result = classifier.classify("massachusetts", {"filing phase": "subsequent"}, "Divorce")
    scope = search.call_args.kwargs
    assert scope["jurisdiction"] == "massachusetts"
    assert scope["filing_phase"] == "subsequent"
    assert {key: scope["selections"][key]["route_key"] for key in ("court", "case category", "case type")} == {
        "court": "staging-court-7",
        "case category": "staging-category-4",
        "case type": "staging-type-9",
    }
    assert result.metadata["code_search_rounds"] == 1
    assert result.selections["filing type"]["route_key"] == "staging-filing-12"


def test_full_classifier_refuses_search_during_court_selection():
    classifier = HierarchicalDocumentClassifier(taxonomy=FakeTaxonomy(), model="test-model")
    with (
        patch(
            "efile.services.taxonomy_classification.chat_completion",
            return_value={"status": "request_more_candidates", "search_query": "court"},
        ) as chat,
        patch("efile.services.taxonomy_classification.search_classification_candidates") as search,
    ):
        result = classifier.classify("massachusetts", {"filing phase": "initial"}, "Court")
    assert result.selections["court"]["status"] == "abstain"
    assert result.metadata["code_search_rounds"] == 0
    assert "search is unavailable" in chat.call_args.kwargs["messages"][-1]["content"]
    search.assert_not_called()
