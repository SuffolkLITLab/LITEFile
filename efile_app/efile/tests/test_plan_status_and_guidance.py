"""Tests for the answers a filer can give about a document, and for the
narrative that explains what their list is and is not.

"I have it" is only one way to be done with a document: plenty are already at
the court from an earlier filing, and plenty are deliberately left until later.
Treating those as gaps means nagging people about work they have already thought
about.
"""

from datetime import date

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingPlan
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.document_checklists import resolve_plan_guidance
from efile.services.filing_plans import (
    checklist_items,
    documents_missing_from_envelope,
    ensure_plan_for_draft,
    plan_progress,
    set_checklist_answers,
)
from efile.workflow import ExistingCase, WorkflowStepKey

CHECKLIST_URL = reverse("document_checklist", kwargs={"jurisdiction": "illinois"})
PLANS_URL = reverse("filing_plans", kwargs={"jurisdiction": "illinois"})


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="status-user", tyler_jurisdiction="illinois")


@pytest.fixture
def draft(user):
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case=ExistingCase.NEW,
        current_step=WorkflowStepKey.DOCUMENT_CHECKLIST,
        court_code="cook:cd1",
        court_name="Cook County Circuit Court - County Division",
        case_category_name="Miscellaneous",
        case_type_name="Name Change",
    )
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="petition.pdf",
        filing_type_name="Petition for Name Change",
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


def item(plan, item_id, draft=None):
    return next(entry for entry in checklist_items(plan, draft) if entry["id"] == item_id)


def configured_plan(draft):
    plan = ensure_plan_for_draft(draft)
    assert plan is not None
    return plan


# --- The answers a filer can give --------------------------------------------


@pytest.mark.django_db
def test_a_document_can_be_already_filed(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"publication_notice": {"status": "filed"}})

    assert item(plan, "publication_notice")["status"] == "filed"
    assert item(plan, "publication_notice")["settled"] is True


@pytest.mark.django_db
def test_a_document_can_be_left_until_later_with_a_date(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"publication_notice": {"status": "later", "due_date": "2026-09-30"}})

    answered = item(plan, "publication_notice")
    assert answered["status"] == "later"
    assert answered["due_date"] == date(2026, 9, 30)
    # Planned is not done: it still counts as outstanding work on the matter.
    assert answered["settled"] is False


@pytest.mark.django_db
def test_a_date_is_optional_and_a_date_we_cannot_read_is_not_kept(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"publication_notice": {"status": "later", "due_date": "next Tuesday"}})

    assert item(plan, "publication_notice")["status"] == "later"
    assert item(plan, "publication_notice")["due_date"] is None
    assert "due_date" not in plan.checklist["publication_notice"]


@pytest.mark.django_db
def test_a_date_is_dropped_when_the_answer_stops_being_later(signed_in):
    plan = configured_plan(signed_in)
    set_checklist_answers(plan, {"publication_notice": {"status": "later", "due_date": "2026-09-30"}})

    set_checklist_answers(plan, {"publication_notice": {"status": "have"}})

    assert item(plan, "publication_notice")["due_date"] is None


@pytest.mark.django_db
def test_an_answer_the_plan_never_offered_is_not_recorded(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"publication_notice": {"status": "burned it"}})

    assert item(plan, "publication_notice")["status"] == ""


@pytest.mark.django_db
def test_plans_written_before_there_were_statuses_still_read(signed_in):
    """Old plans recorded a "complete" flag; they meant "I have it"."""

    plan = configured_plan(signed_in)
    FilingPlan.objects.filter(pk=plan.pk).update(
        checklist={"publication_notice": {"label": "Notice", "requirement": "usually", "complete": True}}
    )
    plan.refresh_from_db()

    assert item(plan, "publication_notice")["status"] == "have"


# --- What that changes about being warned ------------------------------------


@pytest.mark.django_db
def test_a_document_already_filed_is_not_a_gap(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"proposed_order": {"status": "filed"}})

    missing = {entry["id"] for entry in documents_missing_from_envelope(plan, signed_in)}
    assert "proposed_order" not in missing


@pytest.mark.django_db
def test_a_document_left_until_later_is_not_a_gap(signed_in):
    """They have told us where it is. Asking again at the last moment is nagging."""

    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"proposed_order": {"status": "later", "due_date": "2026-10-01"}})

    missing = {entry["id"] for entry in documents_missing_from_envelope(plan, signed_in)}
    assert "proposed_order" not in missing


@pytest.mark.django_db
def test_a_document_in_hand_but_not_attached_is_still_a_gap(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(plan, {"proposed_order": {"status": "have"}})

    missing = {entry["id"]: entry["reason"] for entry in documents_missing_from_envelope(plan, signed_in)}
    assert missing["proposed_order"] == "have"


@pytest.mark.django_db
def test_progress_counts_filed_as_done_and_later_separately(signed_in):
    plan = configured_plan(signed_in)

    set_checklist_answers(
        plan,
        {
            "petition": {"status": "have"},
            "proposed_order": {"status": "filed"},
            "publication_notice": {"status": "later"},
        },
    )

    progress = plan_progress(plan)
    assert progress["complete"] == 2
    assert progress["later"] == 1
    assert progress["outstanding"] == progress["total"] - 3


# --- The screens -------------------------------------------------------------


@pytest.mark.django_db
def test_the_checklist_offers_every_answer(client, signed_in):
    page = client.get(CHECKLIST_URL).content.decode()

    assert "I have it now" in page
    assert "I already filed this" in page
    assert "I will file it later" in page
    assert 'name="due_publication_notice"' in page


@pytest.mark.django_db
def test_answering_on_the_checklist_is_saved(client, signed_in):
    client.post(
        CHECKLIST_URL,
        {
            "action": "save_progress",
            "status_proposed_order": "filed",
            "status_publication_notice": "later",
            "due_publication_notice": "2026-09-30",
        },
    )

    signed_in.refresh_from_db()
    checklist = signed_in.plan.checklist
    assert checklist["proposed_order"]["status"] == "filed"
    assert checklist["publication_notice"]["status"] == "later"
    assert checklist["publication_notice"]["due_date"] == "2026-09-30"


@pytest.mark.django_db
def test_answering_on_the_plans_page_is_saved(client, signed_in):
    plan = configured_plan(signed_in)

    client.post(
        PLANS_URL,
        {
            "action": "save_progress",
            "plan_id": plan.pk,
            "status_publication_notice": "later",
            "due_publication_notice": "2026-09-30",
        },
    )

    plan.refresh_from_db()
    assert plan.checklist["publication_notice"]["status"] == "later"
    assert plan.checklist["publication_notice"]["due_date"] == "2026-09-30"


# --- The narrative about the list --------------------------------------------


@pytest.mark.django_db
def test_a_plan_keeps_what_its_partner_says_about_this_kind_of_filing(signed_in):
    plan = configured_plan(signed_in)

    assert "name change" in plan.guidance["summary"].lower()
    assert plan.guidance["learn_more_url"].startswith("https://")
    assert plan.guidance["learn_more_label"]


@pytest.mark.django_db
def test_the_plans_page_explains_the_list_and_links_onward(client, signed_in):
    plan = configured_plan(signed_in)

    page = client.get(PLANS_URL).content.decode()

    assert "About this list" in page
    assert plan.guidance["learn_more_url"] in page
    # The limits of the list are said plainly, whatever the partner wrote.
    assert "a guide, not legal advice" in page


@pytest.mark.django_db
def test_the_checklist_step_explains_the_list_too(client, signed_in):
    page = client.get(CHECKLIST_URL).content.decode()

    assert "About this list" in page
    assert "a guide, not legal advice" in page


def test_each_side_of_a_case_gets_its_own_explanation():
    landlord = resolve_plan_guidance(
        "illinois",
        court_code="cook:cvd1",
        case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
        filer_role="landlord",
    )
    tenant = resolve_plan_guidance(
        "illinois",
        court_code="cook:cvd1",
        case_type_name="Eviction - Possession - Residential Complaint Filed - Non-Jury",
        filer_role="tenant",
    )

    assert landlord["summary"] != tenant["summary"]
    assert landlord["learn_more_url"] != tenant["learn_more_url"]
    assert tenant["summary"].startswith("Your landlord")


def test_a_learn_more_link_has_to_be_a_web_address(tmp_path, monkeypatch):
    """A "link" that runs script is not a link to a website."""

    import yaml

    from efile.utils.config_loader import JurisdictionConfigLoader

    (tmp_path / "base-case-types.yaml").write_text(yaml.safe_dump({}))
    (tmp_path / "states").mkdir(exist_ok=True)
    (tmp_path / "states" / "testland.yaml").write_text(
        yaml.safe_dump(
            {
                "case_types": {
                    "thing": {
                        "matches": {"names": ["Thing"]},
                        "about": {"summary": "About the thing.", "learn_more_url": "javascript:alert(1)"},
                        "documents": {"a_form": {"label": "A form", "requirement": "always"}},
                    }
                }
            }
        )
    )
    loader = JurisdictionConfigLoader(config_dir=tmp_path)
    monkeypatch.setattr("efile.services.document_checklists.config_loader", loader)

    guidance = resolve_plan_guidance("testland", case_type_name="Thing")

    assert guidance["summary"] == "About the thing."
    assert "learn_more_url" not in guidance


def test_a_case_type_with_nothing_written_about_it_has_no_narrative():
    assert resolve_plan_guidance("illinois", case_type_name="Nothing Configured") == {}
