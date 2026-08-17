"""Tests for a document arriving with the court's name for it already chosen.

Adding a proposed order from the checklist and then being made to pick its
filing type out of forty is the plan failing to finish its own sentence. The
plan knows what the document is, so it can say what the court calls it -- and
when the court calls it nothing, say so by leaving the choice alone.
"""

from unittest.mock import Mock, patch

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.filing_plans import ensure_plan_for_draft, filing_type_for_item
from efile.workflow import ExistingCase, WorkflowStepKey

CHECKLIST_URL = reverse("document_checklist", kwargs={"jurisdiction": "illinois"})

# What Kane County publishes for a change of name, trimmed to what matters here.
KANE_FILING_TYPES = [
    {"code": "6529", "name": "Waiver"},
    {"code": "6714", "name": "Motion"},
    {"code": "25946", "name": "Other Document Not Listed"},
    {"code": "25955", "name": "Petition"},
]


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="filing-type-user", tyler_jurisdiction="illinois")


@pytest.fixture
def draft(user):
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case=ExistingCase.NEW,
        current_step=WorkflowStepKey.DOCUMENT_CHECKLIST,
        court_code="kane",
        court_name="Kane County",
        case_category_code="25827",
        case_category_name="Miscellaneous Remedy",
        case_type_code="10589",
        case_type_name="Change of Name",
    )
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="petition.pdf",
        filing_type_code="25955",
        filing_type_name="Petition",
    )
    return draft


@pytest.fixture
def signed_in(client, user, draft):
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


def court_publishes(filing_types):
    """Stand in for the court's live filing type list."""

    return patch(
        "efile.services.filing_plans.requests.get",
        return_value=Mock(raise_for_status=Mock(), json=Mock(return_value=filing_types)),
    )


def a_document(draft, name="proposed-order.pdf"):
    return FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.SUPPORTING,
        sort_order=0,
        name=name,
        s3_key=f"uploads/{name}",
    )


@pytest.mark.django_db
def test_the_plan_knows_what_the_court_calls_a_proposed_order(signed_in):
    ensure_plan_for_draft(signed_in)

    with court_publishes(KANE_FILING_TYPES):
        code, name = filing_type_for_item(signed_in, "proposed_order")

    assert (code, name) == ("25946", "Other Document Not Listed")


@pytest.mark.django_db
def test_the_most_preferred_name_the_court_offers_wins(signed_in):
    """Configuration lists several names; the court decides which exists."""

    ensure_plan_for_draft(signed_in)

    with court_publishes([{"code": "40001", "name": "Proposed Order"}, *KANE_FILING_TYPES]):
        code, name = filing_type_for_item(signed_in, "proposed_order")

    assert (code, name) == ("40001", "Proposed Order")


@pytest.mark.django_db
def test_a_court_that_names_it_nothing_leaves_the_choice_alone(signed_in):
    """Cook publishes no order or catch-all type for a name change."""

    ensure_plan_for_draft(signed_in)

    with court_publishes([{"code": "78690", "name": "Petition for Name Change"}]):
        assert filing_type_for_item(signed_in, "proposed_order") == ("", "")


@pytest.mark.django_db
def test_an_item_with_no_configured_names_asks_the_court_nothing(signed_in):
    ensure_plan_for_draft(signed_in)

    with court_publishes(KANE_FILING_TYPES) as request:
        assert filing_type_for_item(signed_in, "county_division_cover_sheet") == ("", "")
        assert request.call_count == 0


@pytest.mark.django_db
def test_adding_a_document_from_the_checklist_fills_in_its_filing_type(client, signed_in):
    document = a_document(signed_in)

    with court_publishes(KANE_FILING_TYPES):
        client.post(
            CHECKLIST_URL,
            {"action": "attach_item", "item_id": "proposed_order", "document_id": document.pk},
        )

    document.refresh_from_db()
    assert document.filing_type_code == "25946"
    assert document.filing_type_name == "Other Document Not Listed"


@pytest.mark.django_db
def test_a_filing_type_the_filer_chose_is_never_overwritten(client, signed_in):
    document = a_document(signed_in)
    document.filing_type_code = "6714"
    document.filing_type_name = "Motion"
    document.save()

    with court_publishes(KANE_FILING_TYPES):
        client.post(
            CHECKLIST_URL,
            {"action": "attach_item", "item_id": "proposed_order", "document_id": document.pk},
        )

    document.refresh_from_db()
    assert document.filing_type_name == "Motion"


@pytest.mark.django_db
def test_a_court_lookup_that_fails_still_attaches_the_document(client, signed_in):
    """The court's code service being down is not a reason to lose the file."""

    document = a_document(signed_in)

    with patch("efile.services.filing_plans.requests.get", side_effect=OSError("boom")):
        client.post(
            CHECKLIST_URL,
            {"action": "attach_item", "item_id": "proposed_order", "document_id": document.pk},
        )

    document.refresh_from_db()
    assert document.checklist_item_id == "proposed_order"
    assert document.filing_type_code == ""
