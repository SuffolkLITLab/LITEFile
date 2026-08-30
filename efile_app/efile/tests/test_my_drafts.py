"""The filer's own list of unsent filings.

A draft nobody can see is a draft nobody can finish or throw away. These tests
describe the page that lists them: what it says about each one, which filing
resuming actually opens, and what "throw this away" does to the rest.
"""

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingPlan
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.workflow import ExistingCase, WorkflowStepKey

DRAFTS_URL = reverse("my_drafts", kwargs={"jurisdiction": "illinois"})


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="drafts-user", tyler_jurisdiction="illinois")


def sign_in(client, user):
    client.force_login(user)
    session = client.session
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()


def make_draft(user, **overrides):
    fields = {
        "user": user,
        "jurisdiction": "illinois",
        "existing_case": ExistingCase.NEW,
        "current_step": WorkflowStepKey.UPLOAD_DOCUMENTS,
        "workflow_version": 2,
    }
    fields.update(overrides)
    return FilingDraft.objects.create(**fields)


@pytest.mark.django_db
def test_the_list_says_enough_to_tell_two_drafts_apart(client, user):
    sign_in(client, user)
    plan = FilingPlan.objects.create(user=user, jurisdiction="illinois", title="My name change")
    make_draft(user, plan=plan, court_name="Cook County Circuit Court")
    make_draft(
        user,
        existing_case=ExistingCase.EXISTING,
        docket_number="2024-EV-000123",
        case_title="Blue Harbor LLC v. Ada Torres",
        current_step=WorkflowStepKey.REVIEW,
    )

    content = client.get(DRAFTS_URL).content.decode()

    assert "My name change" in content
    assert "Blue Harbor LLC v. Ada Torres" in content
    assert "2024-EV-000123" in content
    assert "Filing into an existing case" in content
    assert "Cook County Circuit Court" in content
    assert "Review" in content  # where each one left off


@pytest.mark.django_db
def test_resuming_from_the_list_opens_that_draft_and_not_the_newest(client, user):
    sign_in(client, user)
    older = make_draft(user, case_title="The one I want")
    make_draft(user, case_title="The one I touched last")

    response = client.post(DRAFTS_URL, {"action": "resume", "draft_id": older.pk})

    assert response.status_code == 302
    assert f"draft={older.pk}" in response.url
    assert client.session[CURRENT_DRAFT_SESSION_KEY] == older.pk


@pytest.mark.django_db
def test_throwing_a_draft_away_takes_it_out_of_every_list(client, user):
    sign_in(client, user)
    draft = make_draft(user, case_title="Started by mistake")
    FilingDocument.objects.create(draft=draft, role=FilingDocument.Role.LEAD, sort_order=0, name="petition.pdf")
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session.save()

    client.post(DRAFTS_URL, {"action": "delete", "draft_id": draft.pk}, follow=True)

    draft.refresh_from_db()
    assert draft.status == FilingDraft.Status.ABANDONED
    # The browser is no longer pointed at a filing that no longer exists for it.
    assert CURRENT_DRAFT_SESSION_KEY not in client.session
    listed = client.get(DRAFTS_URL)
    assert listed.context["drafts"] == []
    assert "no filings in progress" in listed.content.decode()


@pytest.mark.django_db
def test_a_submitted_filing_is_not_offered_as_a_draft(client, user):
    sign_in(client, user)
    make_draft(user, status=FilingDraft.Status.SUBMITTED, case_title="Already sent")

    assert client.get(DRAFTS_URL).context["drafts"] == []


@pytest.mark.django_db
def test_a_filer_cannot_touch_someone_elses_draft(client, user, django_user_model):
    other = django_user_model.objects.create_user(username="other-drafter", tyler_jurisdiction="illinois")
    theirs = make_draft(other, case_title="Not yours")
    sign_in(client, user)

    response = client.post(DRAFTS_URL, {"action": "delete", "draft_id": theirs.pk}, follow=True)

    theirs.refresh_from_db()
    assert theirs.status == FilingDraft.Status.DRAFT
    assert "no longer here" in response.content.decode()


@pytest.mark.django_db
def test_the_options_page_sends_a_filer_with_several_drafts_to_the_list(client, user):
    sign_in(client, user)
    make_draft(user)
    make_draft(user)

    response = client.get(reverse("efile_options", kwargs={"jurisdiction": "illinois"}))

    assert response.context["draft_count"] == 2
    content = response.content.decode()
    assert DRAFTS_URL in content
    assert "Continue a draft" in content
    assert '<details class="option-card option-disclosure">' in content
    assert '<span class="option-count" aria-hidden="true">2</span>' in content
    assert '<details class="option-card option-disclosure" open>' not in content


@pytest.mark.django_db
def test_my_drafts_needs_a_signed_in_filer(client):
    response = client.get(DRAFTS_URL)

    assert response.status_code == 302
    assert "/login/" in response.url
