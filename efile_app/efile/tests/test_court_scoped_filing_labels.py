import pytest
from django.utils import timezone

from efile.models import FilingCodeIndex, FilingCodeLabel, FilingCodePath
from efile.services.filing_code_labels import LabelCounts, LabelSpool, build_labels, forget_courts
from efile.services.filing_code_search import matching_labels, packed, stems

pytestmark = pytest.mark.django_db


def _index():
    return FilingCodeIndex.objects.create(
        jurisdiction="illinois",
        source_url="https://example.test",
        refreshed_at=timezone.now(),
        rules_digest="test",
        vocabulary={
            "words": ["complaint", "cookalias", "otheralias", "newalias"],
            "tokens": ["complaint", "cookalias", "otheralias", "newalias"],
            "courts": {"il:cook": "Cook County", "il:other": "Other County"},
        },
        court_snapshots={},
    )


def _entry(court, filing_terms):
    return {
        "initial": True,
        "court": {"code": court, "name": court},
        "filing_type": {"code": "complaint", "name": "Complaint"},
        "case_category": {"code": "civil", "name": "Civil"},
        "case_type": {"code": "eviction", "name": "Eviction"},
        "filing_terms": packed(set(stems("Complaint")) | set(stems(filing_terms))),
        "case_terms": packed(set(stems("Civil Eviction"))),
        "search_text": packed(set(stems("Complaint Civil Eviction")) | set(stems(filing_terms))),
    }


def _rows(index):
    return {
        row.filing_terms: row.courts
        for row in FilingCodeLabel.objects.filter(index=index, filing_type_name="Complaint")
    }


def test_same_names_keep_court_scoped_synonyms_separate(monkeypatch):
    monkeypatch.setattr("efile.services.filing_code_search.heading_court_codes", lambda jurisdiction: frozenset())
    index = _index()
    labels = LabelCounts()
    labels.add(_entry("il:cook", "cookalias"))
    labels.add(_entry("il:other", "otheralias"))
    labels.save(index)

    rows = _rows(index)
    assert len(rows) == 2
    assert sorted(rows.values(), key=lambda value: next(iter(value))) == [{"il:cook": 1}, {"il:other": 1}]

    cook, _, _ = matching_labels(index, "cookalias", True)
    other, _, _ = matching_labels(index, "otheralias", True)
    assert [(label.filing_type_name, courts) for label, courts in cook] == [("Complaint", {"il:cook": 1})]
    assert [(label.filing_type_name, courts) for label, courts in other] == [("Complaint", {"il:other": 1})]


def test_incremental_forget_and_rebuild_preserve_distinct_vocabularies():
    index = _index()
    cook = LabelCounts()
    cook.add(_entry("il:cook", "cookalias"))
    cook.save(index)
    other = LabelCounts()
    other.add(_entry("il:other", "otheralias"))
    other.save(index)
    assert len(_rows(index)) == 2

    forget_courts(index, ["il:cook"])
    assert list(_rows(index).values()) == [{"il:other": 1}]

    rebuilt = LabelCounts()
    rebuilt.add(_entry("il:cook", "newalias"))
    rebuilt.save(index)
    assert sorted(_rows(index).values(), key=lambda value: next(iter(value))) == [{"il:cook": 1}, {"il:other": 1}]


def test_spooled_label_build_keeps_same_named_synonyms_separate():
    index = _index()
    spool = LabelSpool()
    try:
        cook = LabelCounts()
        cook.add(_entry("il:cook", "cookalias"))
        other = LabelCounts()
        other.add(_entry("il:other", "otheralias"))
        spool.add(cook)
        spool.add(other)
        spool.save(index)
    finally:
        spool.directory.cleanup()

    assert sorted(_rows(index).values(), key=lambda value: next(iter(value))) == [{"il:cook": 1}, {"il:other": 1}]


def test_build_labels_keeps_same_named_synonyms_separate():
    index = _index()
    for entry in (_entry("il:cook", "cookalias"), _entry("il:other", "otheralias")):
        FilingCodePath.objects.create(index=index, **entry, explanation="", explanation_source="")

    build_labels(index)

    assert sorted(_rows(index).values(), key=lambda value: next(iter(value))) == [{"il:cook": 1}, {"il:other": 1}]


def test_path_alias_court_selectors_do_not_match_other_counties(monkeypatch):
    from copy import deepcopy

    from efile.services import filing_code_search as search

    config = deepcopy(search.rules()[0])
    config["path_aliases"] = [
        {
            "jurisdictions": ["illinois"],
            "initial": False,
            "court_code_prefixes": ["cook:"],
            "filing_type": ["Local filing label"],
            "terms": ["cookalias"],
        },
        {
            "jurisdictions": ["illinois"],
            "initial": False,
            "court_codes": ["cook:dr"],
            "filing_type": ["Local filing label"],
            "terms": ["divisiononly"],
        },
    ]
    monkeypatch.setattr(search, "rules", lambda: (config, "scoped-test"))
    search.path_alias_rules.cache_clear()
    search.path_alias_tokens.cache_clear()
    try:
        token = next(iter(search.stems("cookalias")))
        division = next(iter(search.stems("divisiononly")))

        def aliases(court, initial=False):
            return search.path_alias_tokens("illinois", initial, "Civil", "Case", "Local filing label", court)

        assert token in aliases("cook:dr")
        assert token in aliases("cook:cvd1")
        assert division in aliases("cook:dr")
        assert division not in aliases("cook:cvd1")
        assert token not in aliases("lake")
        assert token not in aliases("notcook:dr")
        assert token not in aliases("cook:dr", initial=True)
    finally:
        search.path_alias_rules.cache_clear()
        search.path_alias_tokens.cache_clear()


def test_cook_family_category_alias_changes_case_words_not_document_identity():
    from efile.services.filing_code_search import indexed_path

    path = {
        "court": {"code": "cook:dr1", "name": "Cook County Domestic Relations District 1"},
        "case_category": {"code": "172833", "name": "Domestic Relations - General Proceedings"},
        "case_type": {"code": "example", "name": "Dissolution of Marriage"},
        "filing_type": {"code": "example", "name": "Unrelated filing"},
    }
    family = next(iter(stems("family")))
    cook = indexed_path("illinois", path, False)
    assert f" {family} " in cook["case_terms"]
    assert f" {family} " not in cook["filing_terms"]
    other = indexed_path("illinois", {**path, "court": {"code": "lake", "name": "Lake"}}, False)
    assert f" {family} " not in other["case_terms"]
    assert cook["filing_type"] == path["filing_type"]
