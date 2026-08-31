from unittest.mock import patch

import pytest

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.party_requirements import party_address_requirement
from efile.services.people import party_is_complete


@pytest.fixture
def draft(django_user_model):
    user = django_user_model.objects.create_user(username="address-rules")
    return FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        court_code="court-1",
        case_type_code="case-1",
        case_type_name="Example case",
    )


@pytest.mark.django_db
def test_blank_address_is_complete_by_default_but_partial_address_is_not(draft):
    party = FilingParty.objects.create(
        draft=draft,
        role="other",
        party_type="DEF",
        first_name="Morgan",
        last_name="Lee",
    )

    assert party_is_complete(party)
    party.state = "IL"
    assert not party_is_complete(party)


@pytest.mark.django_db
def test_live_party_metadata_can_require_the_address(draft):
    party = FilingParty.objects.create(
        draft=draft,
        role="other",
        party_type="DEF",
        first_name="Morgan",
        last_name="Lee",
    )

    requirement = party_address_requirement(
        draft,
        party,
        party_types=[{"code": "DEF", "address_required": True}],
    )

    assert requirement.required


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("rule", "document_values"),
    [
        ({"required_for_party_types": ["DEF"]}, {}),
        ({"required_for_filing_types": ["FILE-1"]}, {"filing_type_code": "FILE-1"}),
        ({"required_for_services": ["SERVICE-1"]}, {"requested_optional_services": ["SERVICE-1"]}),
    ],
)
def test_layered_config_can_require_address_by_party_filing_or_service(draft, rule, document_values):
    party = FilingParty.objects.create(
        draft=draft,
        role="other",
        party_type="DEF",
        first_name="Morgan",
        last_name="Lee",
    )
    if document_values:
        FilingDocument.objects.create(draft=draft, role=FilingDocument.Role.LEAD, **document_values)

    with (
        patch(
            "efile.services.party_requirements.config_loader.load_jurisdiction_config",
            return_value={"defaults": {"party_address": {"required": False}}},
        ),
        patch(
            "efile.services.party_requirements.config_loader.get_case_type_config",
            return_value={"party_address": {**rule, "reason": "This filing needs an address."}},
        ),
    ):
        requirement = party_address_requirement(draft, party)

    assert requirement.required
    assert requirement.reason == "This filing needs an address."
