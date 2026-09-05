import pytest
from django.urls import reverse

from efile.models import FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.workflow import ExistingCase, WorkflowStepKey


def prepare_client(client, django_user_model, *, existing_case=ExistingCase.EXISTING):
    user = django_user_model.objects.create_user(username="case-lookup-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case=existing_case,
    )
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()
    return draft


@pytest.mark.django_db
def test_new_case_skips_case_lookup(client, django_user_model):
    prepare_client(client, django_user_model, existing_case=ExistingCase.NEW)

    response = client.get(reverse("case_lookup", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    assert response.url.partition("?")[0] == reverse("document_checklist", kwargs={"jurisdiction": "illinois"})


@pytest.mark.django_db
def test_case_lookup_result_is_persisted_on_the_draft(client, django_user_model):
    draft = prepare_client(client, django_user_model)

    response = client.post(
        reverse("case_lookup", kwargs={"jurisdiction": "illinois"}),
        data={
            "court": "cook:cvd1",
            "court_name": "Cook County - Municipal Civil - District 1 - Chicago",
            "case_tracking_id": "tracking-123",
            "case_docket_id": "2025MR000123",
            "case_title": "Ada Lovelace v. Example LLC",
            "case_category_code": "MR",
            "case_category_name": "Miscellaneous Remedy",
            "case_type_code": "NC",
            "case_type_name": "Name Change",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["redirect_url"].partition("?")[0] == reverse(
        "case_confirmation",
        kwargs={"jurisdiction": "illinois"},
    )
    draft.refresh_from_db()
    assert draft.current_step == WorkflowStepKey.CASE_CONFIRMATION
    assert draft.previous_case_id == "tracking-123"
    assert draft.docket_number == "2025MR000123"
    assert draft.case_title == "Ada Lovelace v. Example LLC"
    assert draft.case_type_name == "Name Change"


@pytest.mark.django_db
def test_case_confirmation_accepts_case_and_converges_on_checklist(client, django_user_model):
    draft = prepare_client(client, django_user_model)
    draft.previous_case_id = "tracking-123"
    draft.docket_number = "2025MR000123"
    draft.case_title = "Ada Lovelace v. Example LLC"
    draft.save()

    response = client.post(
        reverse("case_confirmation", kwargs={"jurisdiction": "illinois"}),
        {"confirmed": "yes"},
    )

    assert response.status_code == 302
    assert response.url.partition("?")[0] == reverse("document_checklist", kwargs={"jurisdiction": "illinois"})
    draft.refresh_from_db()
    assert draft.current_step == WorkflowStepKey.DOCUMENT_CHECKLIST


@pytest.mark.django_db
def test_case_confirmation_rejection_clears_result_and_returns_to_lookup(client, django_user_model):
    draft = prepare_client(client, django_user_model)
    draft.previous_case_id = "tracking-123"
    draft.docket_number = "2025MR000123"
    draft.case_title = "Wrong case"
    draft.save()

    response = client.post(
        reverse("case_confirmation", kwargs={"jurisdiction": "illinois"}),
        {"confirmed": "no"},
    )

    assert response.status_code == 302
    assert response.url.partition("?")[0] == reverse("case_lookup", kwargs={"jurisdiction": "illinois"})
    draft.refresh_from_db()
    assert draft.previous_case_id == ""
    assert draft.docket_number == ""
    assert draft.case_title == ""
    assert draft.current_step == WorkflowStepKey.CASE_LOOKUP
