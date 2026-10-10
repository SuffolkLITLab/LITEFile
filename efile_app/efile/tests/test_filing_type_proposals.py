import pytest
from django.urls import reverse

from efile.services.filing_type_proposals import current_proposal, resolve_proposal, save_proposal
from efile.tests.test_case_filing_types import confirmed_case as _confirmed_case

confirmed_case = _confirmed_case
pytestmark = pytest.mark.django_db
CHOICES = [{"value": "motion", "text": "Motion to dismiss"}, {"value": "answer", "text": "Answer"}]


def test_user_correction_survives_resume_and_resolves_against_actual_options(confirmed_case):
    draft = confirmed_case
    draft.extracted_guesses = {"filing type": "Complaint"}
    draft.save()
    save_proposal(draft, "Motion to dismiss")
    draft.refresh_from_db()
    assert current_proposal(draft)["source"] == "user"
    assert resolve_proposal(draft, CHOICES) == {"status": "matched", "name": "Motion to dismiss", "value": "motion"}
    assert not draft.documents.get().filing_type_code


def test_unavailable_or_ambiguous_suggestion_is_not_selected(confirmed_case):
    save_proposal(confirmed_case, "Complaint")
    assert resolve_proposal(confirmed_case, CHOICES)["status"] == "unavailable"
    save_proposal(confirmed_case, "Answer")
    assert resolve_proposal(confirmed_case, CHOICES + [{"value": "other", "text": "Answer"}])["status"] == "unavailable"


def test_clearing_a_suggestion_does_not_restore_the_ai_guess(confirmed_case):
    confirmed_case.extracted_guesses = {"filing type": "Complaint"}
    save_proposal(confirmed_case, "")
    assert resolve_proposal(confirmed_case, CHOICES) == {"status": "none"}


def test_replacement_invalidates_a_previous_correction(confirmed_case):
    save_proposal(confirmed_case, "Answer")
    confirmed_case.documents.update(s3_key="replacement.pdf")
    assert current_proposal(confirmed_case) is None


def test_opt_out_keeps_the_ordinary_selection_path(confirmed_case):
    save_proposal(confirmed_case, "Answer")
    confirmed_case.ai_assistance_opted_out = True
    assert resolve_proposal(confirmed_case, CHOICES) == {"status": "none"}


def test_confirm_saves_a_provisional_correction_without_applying_a_code(client, confirmed_case):
    confirmed_case.extracted_guesses = {"filing type": "Complaint"}
    confirmed_case.save()
    response = client.post(
        reverse("extraction_review", kwargs={"jurisdiction": "vermont"}),
        {
            "existing_case": "existing",
            "reviewed_extraction": "yes",
            "proposed_filing_type": "Answer",
        },
    )
    assert response.status_code == 302
    confirmed_case.refresh_from_db()
    assert current_proposal(confirmed_case)["name"] == "Answer"
    assert not confirmed_case.documents.get().filing_type_code
