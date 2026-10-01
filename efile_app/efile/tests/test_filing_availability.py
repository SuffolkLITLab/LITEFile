from unittest.mock import Mock

import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.filing_availability import draft_unavailable_message, filing_unavailable_message
from efile.tests.helpers import reviewed_document


@pytest.fixture
def submission_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="availability-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        existing_case="new",
        court_code="cook:law1",
        court_name="Cook County",
        case_category_code="civil",
        case_type_code="contract",
        case_type_name="Contract",
    )
    reviewed_document(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="Petition.pdf",
        filing_type_code="petition",
        document_type_code="public",
    )
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "test-token"}
    session.save()
    return draft


@pytest.fixture
def configure(monkeypatch):
    def set_config(availability, court="cook:law1"):
        monkeypatch.setattr(
            "efile.services.filing_availability.config_loader.load_jurisdiction_config",
            lambda jurisdiction: {"court_specific_requirements": {court: {"filing_availability": availability}}}
            if jurisdiction == "illinois"
            else {},
        )

    return set_config


def test_default_enabled_and_jurisdiction_and_court_scope(configure):
    configure({"enabled": False})
    assert filing_unavailable_message("illinois", "cook:law1")
    assert not filing_unavailable_message("illinois", "cook:law2")
    assert not filing_unavailable_message("vermont", "cook:law1")


@pytest.mark.parametrize(
    "selector,arguments",
    [
        ("case_categories", {"case_category": "123"}),
        ("case_types", {"case_type": "123"}),
        ("filing_types", {"filing_types": ["unrestricted", "123"]}),
    ],
)
def test_each_selector_matches_codes_including_numeric_yaml(configure, selector, arguments):
    configure({"rules": [{selector: [123], "message": "Scheduling is unavailable."}]})
    assert filing_unavailable_message("illinois", "cook:law1", **arguments) == "Scheduling is unavailable."
    assert not filing_unavailable_message("illinois", "cook:law1")


def test_rules_combine_selectors_and_fall_back_to_court_message(configure):
    configure({"message": "Court notice", "rules": [{"case_types": ["contract"], "filing_types": ["motion"]}]})
    assert not filing_unavailable_message("illinois", "cook:law1", case_type="contract")
    assert (
        filing_unavailable_message("illinois", "cook:law1", case_type="contract", filing_types=["motion"])
        == "Court notice"
    )


def test_county_prefix_is_bounded_and_specific_message_wins(monkeypatch):
    monkeypatch.setattr(
        "efile.services.filing_availability.config_loader.load_jurisdiction_config",
        lambda jurisdiction: {
            "court_specific_requirements": {
                "cook:*": {"filing_availability": {"enabled": False, "message": "County notice"}},
                "cook:law1": {
                    "filing_availability": {
                        "enabled": True,
                        "rules": [{"case_types": ["contract"], "message": "Hearing scheduling is unavailable."}],
                    }
                },
            }
        },
    )
    assert (
        filing_unavailable_message("illinois", "cook:law1", case_type="contract")
        == "Hearing scheduling is unavailable."
    )
    assert filing_unavailable_message("illinois", "cook:law1", case_type="other") == "County notice"
    assert filing_unavailable_message("illinois", "cook:cd1") == "County notice"
    assert not filing_unavailable_message("illinois", "cooksville:law1")


def test_empty_rules_do_not_disable_and_specific_overrides_generic(configure):
    configure({"rules": [{"message": "No selector"}, {"case_types": []}]})
    assert not filing_unavailable_message("illinois", "cook:law1")
    configure({"enabled": False, "message": "Generic", "rules": [{"case_types": ["contract"], "message": "Specific"}]})
    assert filing_unavailable_message("illinois", "cook:law1", case_type="contract") == "Specific"


@pytest.mark.django_db
def test_supporting_document_blocks_envelope_and_removal_restores_filing(configure, submission_draft):
    configure({"rules": [{"filing_types": ["motion"]}]})
    assert not draft_unavailable_message(submission_draft)
    document = FilingDocument.objects.create(
        draft=submission_draft, role="supporting", sort_order=1, filing_type_code="motion"
    )
    assert draft_unavailable_message(submission_draft)
    document.delete()
    assert not draft_unavailable_message(submission_draft)


@pytest.mark.django_db
@pytest.mark.parametrize("view", ["document_checklist", "case_review"])
def test_blocked_page_preserves_draft_and_escapes_message(configure, client, submission_draft, view):
    configure({"rules": [{"case_types": ["contract"], "message": "Scheduling <script>alert(1)</script>"}]})
    response = client.get(reverse(view, kwargs={"jurisdiction": "illinois"}))
    assert response.status_code == 403
    assert b"Scheduling &lt;script&gt;" in response.content
    assert b"Correct case details" in response.content
    submission_draft.refresh_from_db()
    assert submission_draft.status == FilingDraft.Status.DRAFT
    assert submission_draft.documents.exists()


@pytest.mark.django_db
def test_direct_submit_cannot_bypass_new_restriction(configure, client, submission_draft, monkeypatch):
    configure({"rules": [{"case_types": ["contract"], "message": "Hearing scheduling is unavailable."}]})
    forward = Mock()
    monkeypatch.setattr("efile.views.submission.forward_final_filing", forward)
    response = client.post(reverse("submit_final_filing"), {}, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["error_code"] == "submission_filing_unavailable"
    forward.assert_not_called()
    submission_draft.refresh_from_db()
    assert submission_draft.status == FilingDraft.Status.DRAFT


@pytest.mark.django_db
def test_outgoing_payload_codes_are_also_checked(configure, client, submission_draft, monkeypatch):
    from django.test import RequestFactory

    from efile.views.session_api import forward_final_filing

    configure({"rules": [{"case_types": ["contract"], "filing_types": ["blocked"]}]})
    request = RequestFactory().post("/")
    request.user = submission_draft.user
    request.session = client.session
    external = Mock()
    monkeypatch.setattr("requests.post", external)
    response = forward_final_filing(
        request,
        {"efile_data": {"al_court_bundle": {"elements": [{"filing_type": "allowed"}, {"filing_type": "blocked"}]}}},
    )
    assert response.status_code == 403
    external.assert_not_called()


@pytest.mark.django_db
def test_confirm_new_case_keeps_choices_editable_when_blocked(configure, client, submission_draft):
    configure({"rules": [{"case_types": ["blocked"], "message": "Scheduling is unavailable."}]})
    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "illinois"}),
        {
            "existing_case": "new",
            "court_code": "cook:law1",
            "court_name": "Cook County",
            "case_category_code": "civil",
            "case_type_code": "blocked",
            "case_type_name": "Blocked type",
        },
    )
    assert response.status_code == 200
    assert b"Scheduling is unavailable." in response.content
    assert response.context["extraction_context"]["case_type_code"] == "blocked"
    submission_draft.refresh_from_db()
    assert submission_draft.case_type_code == "contract"


@pytest.mark.django_db
def test_existing_case_confirmation_is_blocked_but_search_again_works(configure, client, submission_draft):
    configure({"enabled": False})
    submission_draft.existing_case = "existing"
    submission_draft.previous_case_id = "case-123"
    submission_draft.docket_number = "2026-CV-123"
    submission_draft.save()
    url = reverse("case_confirmation", kwargs={"jurisdiction": "illinois"})
    response = client.get(url)
    assert response.context["availability_message"]
    assert b'value="yes"' in response.content
    assert client.post(url, {"confirmed": "yes"}).status_code == 403
    assert client.post(url, {"confirmed": "no"}).status_code == 302


@pytest.mark.django_db
def test_organize_blocks_supporting_type_but_allows_correction(configure, client, submission_draft):
    configure({"rules": [{"filing_types": ["motion"], "message": "Scheduling is unavailable."}]})
    document = submission_draft.documents.first()
    url = reverse("organize_documents", kwargs={"jurisdiction": "illinois"})
    details = {"id": document.pk, "filing_type": "motion", "document_type": "public"}
    payload = {"main_document_id": document.pk, "documents": [details]}
    response = client.post(url, payload, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["error"] == "Scheduling is unavailable."
    assert b"Scheduling is unavailable." in client.get(url).content
    details["filing_type"] = "petition"
    assert client.post(url, payload, content_type="application/json").status_code == 200


@pytest.mark.django_db
def test_claim_rechecks_availability(configure, submission_draft):
    from efile.views.submission import _claim_for_submission

    configure({"enabled": False, "message": "Disabled since review"})
    with pytest.raises(ValueError, match="Disabled since review"):
        _claim_for_submission(submission_draft, {})
    submission_draft.refresh_from_db()
    assert submission_draft.status == FilingDraft.Status.DRAFT


@pytest.mark.django_db
def test_live_api_checks_partial_choices_and_multiple_filing_types(configure, client):
    configure({"enabled": False, "message": "Court disabled"})
    url = reverse("api:filing_availability")
    params = {"jurisdiction": "illinois", "court": "cook:law1"}
    response = client.get(url, params)
    assert response.json() == {"success": True, "available": False, "message": "Court disabled"}
    assert "no-store" in response.headers["Cache-Control"]
    configure({"rules": [{"filing_types": ["motion"], "message": "Scheduling unavailable"}]})
    assert client.get(url, params).json()["available"]
    params["filing_type"] = ["petition", "motion"]
    assert not client.get(url, params).json()["available"]


@pytest.mark.django_db
def test_live_api_rejects_unknown_jurisdiction(client):
    assert client.get(reverse("api:filing_availability"), {"jurisdiction": "unknown"}).status_code == 400
