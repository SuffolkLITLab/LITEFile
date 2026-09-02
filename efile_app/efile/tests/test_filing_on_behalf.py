"""Filing for a party you are not.

Being the person filing and being a party to the case are two different
things. Most people using this are self-represented and are both, but a parent
files for a child, a neighbour helps someone answer an eviction, and neither of
them belongs in the caption. Tyler asks only who a filing is made *on behalf
of*, and keeps the person filing separately as the envelope's lead contact.

These tests cover the answer being optional, the follow-up question it opens,
and the screens downstream that used to insist the filer was a party.
"""

import re
from unittest.mock import patch

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.drafts import read_case_data
from efile.services.people import NOT_A_PARTY, absorb_filer_duplicates, filing_parties, party_is_complete
from efile.workflow import ExistingCase, WorkflowStepKey

PARTIES_URL = reverse("parties", kwargs={"jurisdiction": "illinois"})
PAYMENT_URL = reverse("payment", kwargs={"jurisdiction": "illinois"})
REVIEW_URL = reverse("case_review", kwargs={"jurisdiction": "illinois"})

NOTICE_EMAIL = "helper@example.com"

PARTY_TYPES = [
    {"code": "plaintiff", "name": "Plaintiff", "required": True},
    {"code": "defendant", "name": "Defendant", "required": True},
]


@pytest.fixture
def draft(client, django_user_model):
    """A neighbour, signed in, helping someone else answer an eviction."""

    user = django_user_model.objects.create_user(username="helper", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case=ExistingCase.NEW,
        court_code="cook:cvd1",
        case_type_code="NC",
        case_type_name="Name Change",
        current_step=WorkflowStepKey.PARTIES,
        document_checklist_acknowledged=True,
    )
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="answer.pdf",
        filing_type_code="90001",
        filing_type_name="Answer",
        document_type_code="public",
    )
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


def make_filer(draft, **overrides):
    values = {
        "first_name": "Helper",
        "last_name": "Neighbor",
        "email": "helper@example.com",
        "address_line_1": "1 Main Street",
        "city": "Chicago",
        "state": "IL",
        "zip_code": "60601",
    }
    values.update(overrides)
    return FilingParty.objects.create(draft=draft, role="filer", sort_order=0, **values)


def make_party(draft, sort_order, **overrides):
    values = {
        "party_type": "defendant",
        "party_type_name": "Defendant",
        "first_name": "Real",
        "last_name": "Tenant",
        "address_line_1": "2 Elm Street",
        "city": "Chicago",
        "state": "IL",
        "zip_code": "60601",
    }
    values.update(overrides)
    return FilingParty.objects.create(draft=draft, role="other", sort_order=sort_order, **values)


def both_sides(draft):
    """A roster the court's required party types are already satisfied by."""

    tenant = make_party(draft, 0)
    landlord = make_party(
        draft,
        1,
        party_type="plaintiff",
        party_type_name="Plaintiff",
        first_name="",
        last_name="",
        organization_name="Landlord LLC",
    )
    return tenant, landlord


def post_parties(client, **data):
    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        return client.post(PARTIES_URL, data)


# --- Saying you are not a party ----------------------------------------------


@pytest.mark.django_db
def test_a_filer_who_is_not_a_party_names_who_they_are_filing_for(client, draft):
    filer = make_filer(draft)
    tenant, landlord = both_sides(draft)

    response = post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email=NOTICE_EMAIL)

    filer.refresh_from_db()
    tenant.refresh_from_db()
    landlord.refresh_from_db()
    draft.refresh_from_db()
    assert response.status_code == 302
    # Past the people step rather than back into it.
    assert draft.current_step != WorkflowStepKey.PARTIES
    assert filer.party_type == ""
    assert filer.is_filing_party is False
    assert tenant.is_filing_party is True
    assert landlord.is_filing_party is False
    assert filing_parties(draft) == [tenant]


@pytest.mark.django_db
def test_saying_you_are_not_a_party_without_naming_anyone_is_refused(client, draft):
    """Tyler needs a party to file on behalf of. Nobody is not an answer."""

    filer = make_filer(draft)
    tenant, _landlord = both_sides(draft)

    response = post_parties(client, filer_party_type=NOT_A_PARTY)

    filer.refresh_from_db()
    tenant.refresh_from_db()
    assert response.status_code == 200
    assert "Choose who you are filing for." in response.content.decode()
    assert tenant.is_filing_party is False


@pytest.mark.django_db
def test_a_refused_answer_stays_on_the_screen_with_the_error(client, draft):
    """Otherwise the follow-up question hides itself again and the filer has
    to work out that they must re-pick the answer they already gave."""

    make_filer(draft)
    both_sides(draft)

    content = post_parties(client, filer_party_type=NOT_A_PARTY).content.decode()

    still_chosen = re.search(rf'value="{NOT_A_PARTY}"[^>]*checked', content)
    assert still_chosen is not None
    assert re.search(r'id="filing-for"(?![^>]*hidden)', content) is not None


@pytest.mark.django_db
def test_an_answer_of_neither_kind_is_still_refused(client, draft):
    make_filer(draft)
    both_sides(draft)

    response = post_parties(client, filer_party_type="")

    assert response.status_code == 200
    assert "Choose your role in this case" in response.content.decode()


@pytest.mark.django_db
def test_someone_can_be_filed_for_by_two_co_parties_at_once(client, draft):
    filer = make_filer(draft)
    tenant, landlord = both_sides(draft)

    post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=[tenant.pk, landlord.pk], notice_email=NOTICE_EMAIL)

    assert {party.pk for party in filing_parties(draft)} == {tenant.pk, landlord.pk}
    filer.refresh_from_db()
    assert filer.is_filing_party is False


# --- Changing your mind ------------------------------------------------------


@pytest.mark.django_db
def test_becoming_a_party_takes_the_filing_back_from_who_you_named(client, draft):
    """Otherwise the envelope would name two filing parties, one of them stale."""

    filer = make_filer(draft)
    tenant, _landlord = both_sides(draft)
    post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email=NOTICE_EMAIL)

    post_parties(client, filer_party_type="defendant")

    filer.refresh_from_db()
    tenant.refresh_from_db()
    assert filer.party_type == "defendant"
    assert filer.is_filing_party is True
    assert tenant.is_filing_party is False
    assert filing_parties(draft) == [filer]


@pytest.mark.django_db
def test_filing_for_someone_else_gives_up_your_own_party_type(client, draft):
    filer = make_filer(draft, party_type="defendant", party_type_name="Defendant", is_filing_party=True)
    tenant, _landlord = both_sides(draft)

    post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email=NOTICE_EMAIL)

    filer.refresh_from_db()
    assert filer.party_type == ""
    assert filer.party_type_name == ""
    assert filer.is_filing_party is False


# --- What the screens say ----------------------------------------------------


@pytest.mark.django_db
def test_the_role_question_offers_filing_for_someone_else(client, draft):
    make_filer(draft)
    both_sides(draft)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        response = client.get(PARTIES_URL)

    content = response.content.decode()
    assert f'value="{NOT_A_PARTY}"' in content
    assert "I am filing for someone else" in content
    assert "Who are you filing for?" in content


@pytest.mark.django_db
def test_the_party_list_offers_to_add_you_while_you_are_not_a_party(client, draft):
    """Issue #207: adding yourself should be one button, not a retyped form."""

    make_filer(draft)
    both_sides(draft)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        not_a_party = client.get(PARTIES_URL).content.decode()

    FilingParty.objects.filter(draft=draft, role="filer").update(party_type="defendant")
    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        already_a_party = client.get(PARTIES_URL).content.decode()

    assert 'id="add-me-as-party"' in not_a_party
    assert 'id="add-me-as-party"' not in already_a_party


@pytest.mark.django_db
def test_a_party_nobody_has_named_is_not_offered_as_who_you_are_filing_for(client, draft):
    """A blank row the court's required-party rule made is not yet anybody."""

    make_filer(draft)
    named = make_party(draft, 0)
    FilingParty.objects.create(draft=draft, role="other", sort_order=1, party_type="plaintiff")

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        response = client.get(PARTIES_URL)

    content = response.content.decode()
    offered = re.findall(r'name="filing_for"\s+value="(\d+)"', content)
    assert offered == [str(named.pk)]


@pytest.mark.django_db
def test_the_add_a_person_screen_offers_actually_this_is_me(client, draft):
    make_filer(draft)
    blank = FilingParty.objects.create(draft=draft, role="other", sort_order=0)

    with patch("efile.views.party_details.get_party_types", return_value=PARTY_TYPES):
        url = f"{reverse('party_details', kwargs={'jurisdiction': 'illinois'})}?party={blank.pk}"
        response = client.get(url)

    assert "This party is me" in response.content.decode()


@pytest.mark.django_db
def test_saying_a_new_party_is_you_drops_the_row_instead_of_duplicating_you(client, draft):
    """The filer is already on the draft once; a second copy of them reaches
    the court as two people with the same name."""

    make_filer(draft)
    blank = FilingParty.objects.create(draft=draft, role="other", sort_order=0)

    response = post_parties(client, action="claim_party", party_id=blank.pk)

    assert response.status_code == 302
    assert response.url.endswith("#your-role")
    assert not FilingParty.objects.filter(pk=blank.pk).exists()


# --- The screens that used to insist ----------------------------------------


@pytest.mark.django_db
def test_a_filer_who_is_not_a_party_is_not_missing_their_own_details(client, draft):
    """Their name and address belong to the contact record, not the caption,
    and the party-details screen has nothing to ask them for."""

    filer = make_filer(draft)

    assert party_is_complete(filer, draft=draft, party_types=PARTY_TYPES) is True


@pytest.mark.django_db
def test_a_filer_who_is_not_a_party_reaches_payment(client, draft):
    filer = make_filer(draft)
    tenant, _landlord = both_sides(draft)
    tenant.is_filing_party = True
    tenant.save(update_fields=["is_filing_party"])

    response = client.get(PAYMENT_URL)

    assert response.status_code == 200
    assert filer.party_type == ""


@pytest.mark.django_db
def test_review_says_who_the_filing_is_for_and_offers_to_add_you(client, draft):
    make_filer(draft)
    tenant, _landlord = both_sides(draft)
    tenant.is_filing_party = True
    tenant.save(update_fields=["is_filing_party"])
    draft.selected_payment_account_id = "pay-1"
    draft.selected_payment_account_name = "Card"
    draft.save(update_fields=["selected_payment_account_id", "selected_payment_account_name"])

    content = client.get(REVIEW_URL).content.decode()

    assert "You are not a party in this case" in content
    assert "Real Tenant" in content
    assert "Add me as a party" in content


@pytest.mark.django_db
def test_folding_a_party_who_is_you_keeps_the_filing_on_behalf_of_someone(draft):
    """The roster's copy of the filer is folded into the filer's own row once
    they say they are a party. The envelope has to come out on behalf of
    somebody all the same."""

    filer = make_filer(draft, first_name="Jamie", last_name="Rivera", party_type="defendant")
    twin = make_party(draft, 0, first_name="Jamie", last_name="Rivera", is_filing_party=True)

    absorb_filer_duplicates(draft)

    filer.refresh_from_db()
    assert not FilingParty.objects.filter(pk=twin.pk).exists()
    assert filing_parties(draft) == [filer]


# --- Drafts from before the question existed ---------------------------------


@pytest.mark.django_db
def test_a_draft_answered_before_this_question_still_files_as_the_filer(client, draft):
    """Back then a filer with a party type was the only possible filing party,
    so that is what their unmarked draft still means."""

    filer = make_filer(draft, party_type="defendant", party_type_name="Defendant")

    assert filer.is_filing_party is False
    assert filing_parties(draft) == [filer]


# --- Where notices about the case go -----------------------------------------


@pytest.mark.django_db
def test_the_notice_address_is_offered_filled_in_with_the_filers_own(client, draft):
    make_filer(draft, email="helper@example.com")
    both_sides(draft)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        content = client.get(PARTIES_URL).content.decode()

    assert "Where should notices about this case go?" in content
    assert re.search(r'name="notice_email"[^>]*value="helper@example\.com"', content) is not None


@pytest.mark.django_db
def test_a_notice_address_can_be_someone_other_than_the_filer(client, draft):
    """The point of asking: the court may need to write to the party, or to
    whoever handles their mail, rather than to the person filing."""

    make_filer(draft)
    tenant, _landlord = both_sides(draft)

    post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email="tenant@example.com")

    draft.refresh_from_db()
    assert draft.notice_email == "tenant@example.com"


@pytest.mark.django_db
def test_filing_for_someone_else_without_any_notice_address_is_refused(client, draft):
    make_filer(draft)
    tenant, _landlord = both_sides(draft)

    response = post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email="")

    tenant.refresh_from_db()
    assert response.status_code == 200
    assert "Give an email address for notices" in response.content.decode()
    assert tenant.is_filing_party is False


@pytest.mark.django_db
def test_a_notice_address_that_is_not_an_address_is_refused(client, draft):
    make_filer(draft)
    tenant, _landlord = both_sides(draft)

    response = post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email="not an email")

    assert response.status_code == 200
    assert "Give an email address for notices" in response.content.decode()


@pytest.mark.django_db
def test_becoming_a_party_stops_naming_a_separate_notice_address(client, draft):
    """It applied to a filing on someone else's behalf. There isn't one now."""

    make_filer(draft)
    tenant, _landlord = both_sides(draft)
    post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=tenant.pk, notice_email="tenant@example.com")

    post_parties(client, filer_party_type="defendant")

    draft.refresh_from_db()
    assert draft.notice_email == ""


@pytest.mark.django_db
def test_review_shows_where_notices_go_with_a_way_to_change_it(client, draft):
    make_filer(draft)
    tenant, _landlord = both_sides(draft)
    tenant.is_filing_party = True
    tenant.save(update_fields=["is_filing_party"])
    draft.notice_email = "tenant@example.com"
    draft.selected_payment_account_id = "pay-1"
    draft.selected_payment_account_name = "Card"
    draft.save(update_fields=["notice_email", "selected_payment_account_id", "selected_payment_account_name"])

    content = client.get(REVIEW_URL).content.decode()

    assert "Notices about this case go to tenant@example.com" in content
    assert "#notice_email" in content


@pytest.mark.django_db
def test_the_notice_address_reaches_the_filing_payload(client, draft):
    make_filer(draft)
    tenant, _landlord = both_sides(draft)
    tenant.is_filing_party = True
    tenant.save(update_fields=["is_filing_party"])
    draft.notice_email = "tenant@example.com"
    draft.save(update_fields=["notice_email"])

    assert read_case_data(draft)["notice_email"] == "tenant@example.com"


# --- The document naming the filer -------------------------------------------


@pytest.mark.django_db
def test_a_caption_party_with_the_filers_name_is_offered_as_them(client, draft):
    make_filer(draft, first_name="Jamie", last_name="Rivera")
    twin = make_party(draft, 0, first_name="Jamie", last_name="Rivera")
    make_party(
        draft,
        1,
        party_type="plaintiff",
        party_type_name="Plaintiff",
        first_name="",
        last_name="",
        organization_name="Landlord LLC",
    )

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        content = client.get(PARTIES_URL).content.decode()

    assert "Jamie Rivera" in content
    assert "Is this you?" in content
    assert f'name="party_id" value="{twin.pk}"' in content
    # The concrete suggestion replaces the vaguer one rather than joining it.
    assert 'id="apply-party-type-guess"' not in content


@pytest.mark.django_db
def test_confirming_that_party_is_you_adopts_their_role_and_stops_listing_them(client, draft):
    filer = make_filer(draft, first_name="Jamie", last_name="Rivera")
    twin = make_party(draft, 0, first_name="Jamie", last_name="Rivera")

    response = post_parties(client, action="claim_party", party_id=twin.pk)

    filer.refresh_from_db()
    assert response.status_code == 302
    assert response.url.endswith("#your-role")
    assert not FilingParty.objects.filter(pk=twin.pk).exists()
    assert filer.party_type == "defendant"
    assert filer.is_filing_party is True
    assert filing_parties(draft) == [filer]


@pytest.mark.django_db
def test_a_party_who_shares_the_filers_name_is_left_alone_until_they_say_so(client, draft):
    """Saying nothing is not saying yes. Two people share a name, and someone
    filing for a relative they are named after is why this screen exists."""

    make_filer(draft, first_name="Jamie", last_name="Rivera")
    twin = make_party(draft, 0, first_name="Jamie", last_name="Rivera")

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        client.get(PARTIES_URL)

    assert FilingParty.objects.filter(pk=twin.pk).exists()


@pytest.mark.django_db
def test_the_suggestion_stops_once_the_filer_has_answered_for_themselves(client, draft):
    """A filer who said they are filing for someone else has answered the
    question, and should not be asked it again every time they come back."""

    make_filer(draft, first_name="Jamie", last_name="Rivera")
    twin = make_party(draft, 0, first_name="Jamie", last_name="Rivera")
    make_party(
        draft,
        1,
        party_type="plaintiff",
        party_type_name="Plaintiff",
        first_name="",
        last_name="",
        organization_name="Landlord LLC",
    )
    post_parties(client, filer_party_type=NOT_A_PARTY, filing_for=twin.pk, notice_email=NOTICE_EMAIL)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        content = client.get(PARTIES_URL).content.decode()

    assert "Is this you?" not in content


# --- Parties nobody added ----------------------------------------------------


@pytest.mark.django_db
def test_a_party_started_and_never_named_does_not_stay_on_the_list(client, draft):
    """Adding a person makes the row before the form that names them, so
    leaving without saving used to strand a nameless entry on the list."""

    make_filer(draft)
    both_sides(draft)
    abandoned = FilingParty.objects.create(draft=draft, role="other", sort_order=9)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        client.get(PARTIES_URL)

    assert not FilingParty.objects.filter(pk=abandoned.pk).exists()


@pytest.mark.django_db
def test_the_courts_own_required_party_placeholder_is_not_swept_up(client, draft):
    """It is nameless for a different reason: the court requires that party,
    and the filer is on their way to naming them."""

    make_filer(draft)
    placeholder = FilingParty.objects.create(
        draft=draft, role="other", sort_order=9, party_type="plaintiff", party_type_name="Plaintiff"
    )

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        client.get(PARTIES_URL)

    assert FilingParty.objects.filter(pk=placeholder.pk).exists()


# --- Becoming one of the parties the document already named ------------------


@pytest.mark.django_db
def test_every_listed_party_can_be_claimed_as_you(client, draft):
    """The court's required parties are routinely all taken by people the
    document named, so being one of them is claiming a row rather than adding
    another person -- which would file a second plaintiff nobody wanted."""

    make_filer(draft)
    tenant, landlord = both_sides(draft)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        content = client.get(PARTIES_URL).content.decode()

    claimable = set(re.findall(r'name="party_id" value="(\d+)"', content))
    assert claimable == {str(tenant.pk), str(landlord.pk)}
    assert content.count(">This is me</button>") == 2
    # And the list says so, for a filer who would otherwise add themselves again.
    assert "If one of the people below is you" in content


@pytest.mark.django_db
def test_claiming_a_detected_party_takes_their_role_and_drops_the_row(client, draft):
    filer = make_filer(draft)
    tenant, landlord = both_sides(draft)

    post_parties(client, action="claim_party", party_id=tenant.pk)

    filer.refresh_from_db()
    assert filer.party_type == "defendant"
    assert filer.party_type_name == "Defendant"
    assert filer.is_filing_party is True
    assert not FilingParty.objects.filter(pk=tenant.pk).exists()
    assert FilingParty.objects.filter(pk=landlord.pk).exists()
    assert filing_parties(draft) == [filer]


@pytest.mark.django_db
def test_a_filer_who_is_already_a_party_is_not_offered_more_of_them(client, draft):
    make_filer(draft, party_type="defendant", party_type_name="Defendant")
    both_sides(draft)

    with patch("efile.views.parties.get_party_types", return_value=PARTY_TYPES):
        content = client.get(PARTIES_URL).content.decode()

    assert "This is me" not in content


@pytest.mark.django_db
def test_the_party_details_screen_offers_it_for_a_party_with_a_name(client, draft):
    """A filer sent to check a detected party's details is exactly who needs
    to be able to say that the party is them."""

    make_filer(draft)
    tenant, _landlord = both_sides(draft)

    with patch("efile.views.party_details.get_party_types", return_value=PARTY_TYPES):
        url = f"{reverse('party_details', kwargs={'jurisdiction': 'illinois'})}?party={tenant.pk}"
        content = client.get(url).content.decode()

    assert "This party is me" in content


@pytest.mark.django_db
def test_claiming_a_party_with_no_role_yet_leaves_the_role_question_to_answer(client, draft):
    """Nothing to adopt: the filer should not come out of it as a filing party
    with no court role, which the payload cannot describe."""

    filer = make_filer(draft)
    blank = FilingParty.objects.create(draft=draft, role="other", sort_order=4)

    post_parties(client, action="claim_party", party_id=blank.pk)

    filer.refresh_from_db()
    assert filer.party_type == ""
    assert filer.is_filing_party is False
    assert not FilingParty.objects.filter(pk=blank.pk).exists()
