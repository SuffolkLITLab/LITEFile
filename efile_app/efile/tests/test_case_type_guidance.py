"""Case facets distinguish real labels without guessing missing information."""

import pytest

from efile.services.case_type_guidance import (
    amount_options,
    case_guidance,
    case_topic,
    claim_range,
    facet_metadata,
    guidance_config,
    matches_amount,
    matches_case_filters,
    topic_config,
    validate_case_filters,
)

EXAMPLES = [
    ("eviction", "Eviction", "Residential - Possession Only", "property", "residential"),
    ("foreclosure", "Foreclosure", "Residential Mortgage Foreclosure", "property", "residential"),
    ("debt", "Civil", "Credit card debt", "issue", "card"),
    ("small_claims", "Small Claims", "Contract ($250.01 to $1,000)", "issue", "contract"),
    ("contract", "Civil", "Contract - Construction", "issue", "services"),
    ("personal_injury", "Personal Injury", "Motor Vehicle", "issue", "vehicle"),
    ("property_damage", "Property Damage", "Vehicle Property Damage", "property", "vehicle"),
    ("replevin", "Civil", "Replevin", "procedure", "replevin"),
    ("divorce", "Dissolution", "Dissolution with children", "children", "with"),
    ("parentage", "Family", "Establish Parentage", "issue", "establish"),
    ("parenting", "Family", "Parenting time", "issue", "time"),
    ("child_support", "Family", "Interstate child support", "issue", "interstate"),
    ("protection", "Protection", "Stalking no contact", "issue", "stalking"),
    ("adult_guardianship", "Adult Guardianship", "Guardianship of the estate", "scope", "financial"),
    ("minor_guardianship", "Minor Guardianship", "Temporary guardianship of minor", "duration", "temporary"),
    ("probate", "Probate", "Will contest", "issue", "contest"),
    ("name_change", "Miscellaneous", "Adult name change", "person", "adult"),
    ("adoption", "Adoption", "Related adult adoption", "relationship", "related"),
    ("administrative_review", "Administrative Review", "Unemployment", "agency", "benefits"),
    ("employment", "Civil", "Unpaid wages", "issue", "wages"),
]


@pytest.mark.parametrize("jurisdiction", ["illinois", "massachusetts", "vermont"])
@pytest.mark.parametrize(("topic", "category", "name", "facet", "value"), EXAMPLES)
def test_twenty_case_families_have_working_contextual_facets(jurisdiction, topic, category, name, facet, value):
    guidance = case_guidance(jurisdiction, category, name, "Complaint")
    assert guidance["topic"] == topic
    assert guidance[facet] == value
    assert guidance["text"] and guidance["source"].startswith("https://")
    label = {"category": category, "case_type": name, "name": "Complaint"}
    metadata = facet_metadata(jurisdiction, "", [label], topic)
    assert any(item["key"] == facet for item in metadata["case_facets"])
    assert matches_case_filters(guidance, topic=topic, filters={facet: value})
    assert not matches_case_filters(guidance, topic=topic, filters={facet: "different"})


def test_catalog_is_complete_and_exclusions_are_not_positive_matches():
    assert set(guidance_config()["topics"]) == {row[0] for row in EXAMPLES}
    assert case_topic("illinois", "Small Claims", "Contract - Employment") == "small_claims"
    assert (
        case_topic("illinois", "Civil", "Contract - Other (Excluding Business/Employment Dispute and Debt Collection)")
        == "contract"
    )
    assert (
        case_guidance("illinois", "Employment", "Employment - Other (Excluding Discrimination)")["issue"] == "unknown"
    )
    assert case_guidance("illinois", "Contracts", "Commercial")["topic"] == "contract"
    assert case_guidance("illinois", "Unknown category", "Other") == {}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Small Claims ($2,500.01 to $10K)", (250001, 1000000)),
        ("Small claims (Up to $2,500)", (0, 250000)),
        ("Small Claims $1,001 to $5,000", (100100, 500000)),
        ("Small claims less than $500", (0, 49999)),
        ("Small claims $500 or less", (0, 50000)),
        ("Small claims over $5,000", (500001, None)),
        ("Small Claims", None),
        ("Filing fee $120", None),
        ("Claim 12-34", None),
    ],
)
def test_claim_range_parsing(name, expected):
    assert claim_range(name) == expected


def test_amount_bands_are_disjoint_and_preserve_unknown_codes():
    labels = [
        {"category": "Small Claims", "case_type": name, "name": "Complaint"}
        for name in [
            "Contract (Up to $2,500)",
            "Contract ($2,500.01 to $10K)",
            "Other",
        ]
    ]
    assert amount_options(labels) == [
        {"value": "0:250000", "label": "Up to $2,500"},
        {"value": "250001:1000000", "label": "$2,500.01–$10,000"},
    ]
    assert matches_amount(labels[0], "250000:250000")
    assert not matches_amount(labels[0], "250001:1000000")
    assert matches_amount(labels[1], "250001:1000000")
    assert matches_amount(labels[2], "250001:1000000")
    assert amount_options(labels[:1]) == []


def test_amount_metadata_is_state_specific_and_only_shown_when_useful():
    labels = [
        {"category": "Small Claims", "case_type": name, "name": "Complaint"}
        for name in ["Up to $1,000", "$1,000.01 to $5,000"]
    ]
    for jurisdiction, text in [("illinois", "$10,000"), ("massachusetts", "$7,000"), ("vermont", "medical debt")]:
        data = facet_metadata(jurisdiction, "small claims", labels)
        amount = next(facet for facet in data["case_facets"] if facet["key"] == "amount")
        assert amount["control"] == "select" and text in amount["help"]
    assert all(
        facet["key"] != "amount" for facet in facet_metadata("illinois", "small claims", labels[:1])["case_facets"]
    )


@pytest.mark.parametrize(
    ("topic", "filters"),
    [
        ("small_claims", {"amount": "x"}),
        ("small_claims", {"amount": "500:100"}),
        ("divorce", {"amount": "0:500"}),
        ("eviction", {"children": "with"}),
        ("no_such_topic", {}),
        ("", {"role": "tenant"}),
        ("all", {"role": "tenant"}),
        ("eviction", []),
        ("eviction", {"role": ["tenant"]}),
    ],
)
def test_invalid_contextual_filters_are_rejected(topic, filters):
    with pytest.raises(ValueError):
        validate_case_filters("illinois", topic, filters)


def test_local_description_precedence(monkeypatch):
    config = guidance_config()["topics"]["name_change"]
    monkeypatch.setitem(
        config["jurisdictions"],
        "illinois",
        {
            "text": "State wording.",
            "counties": {
                "Example": {"court_names": ["Example Court", "Example Other Court"], "text": "County wording."}
            },
            "courts": {"Example Court": {"text": "Court wording."}},
        },
    )
    topic_config.cache_clear()
    case_guidance.cache_clear()
    try:
        assert case_guidance("illinois", "Civil", "Name change", court_name="Example Court")["text"] == "Court wording."
        assert (
            case_guidance("illinois", "Civil", "Name change", court_name="Example Other Court")["text"]
            == "County wording."
        )
        assert case_guidance("illinois", "Civil", "Name change", court_name="Elsewhere")["text"] == "State wording."
    finally:
        topic_config.cache_clear()
        case_guidance.cache_clear()
