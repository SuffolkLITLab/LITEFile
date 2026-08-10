from types import SimpleNamespace

import pytest
from django.urls import reverse

from efile.workflow import (
    FILING_WORKFLOW,
    LEGACY_WORKFLOW,
    ExistingCase,
    WorkflowStepKey,
    get_next_step,
    get_previous_step,
    get_resume_step_url,
    get_step,
    get_step_url,
    get_visible_workflow,
    get_workflow_context,
    get_workflow_steps,
    legacy_existing_case_value,
    normalize_existing_case,
)


def draft(**overrides):
    values = {
        "current_step": WorkflowStepKey.FILING_PATH,
        "workflow_version": 2,
        "existing_case": ExistingCase.NEW,
        "case_questions_required": False,
        "parties": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def keys(workflow):
    return [step.key for step in workflow]


def test_target_workflow_declares_every_reorganized_screen():
    assert get_workflow_steps() == FILING_WORKFLOW
    assert keys(FILING_WORKFLOW) == [
        WorkflowStepKey.OPTIONS,
        WorkflowStepKey.FILING_PATH,
        WorkflowStepKey.UPLOAD_DOCUMENTS,
        WorkflowStepKey.EXTRACTION_REVIEW,
        WorkflowStepKey.CASE_LOOKUP,
        WorkflowStepKey.CASE_CONFIRMATION,
        WorkflowStepKey.DOCUMENT_CHECKLIST,
        WorkflowStepKey.ORGANIZE_DOCUMENTS,
        WorkflowStepKey.YOUR_INFORMATION,
        WorkflowStepKey.PARTIES,
        WorkflowStepKey.PARTY_DETAILS,
        WorkflowStepKey.CASE_QUESTIONS,
        WorkflowStepKey.PAYMENT,
        WorkflowStepKey.REVIEW,
        WorkflowStepKey.CONFIRMATION,
    ]


def test_legacy_drafts_keep_the_current_linear_route_during_migration():
    legacy_draft = draft(current_step=WorkflowStepKey.DOCUMENTS, workflow_version=1)

    assert get_visible_workflow(legacy_draft) == LEGACY_WORKFLOW
    assert get_previous_step(WorkflowStepKey.PAYMENT, legacy_draft).key == WorkflowStepKey.DOCUMENTS
    assert get_next_step(WorkflowStepKey.PAYMENT, legacy_draft).key == WorkflowStepKey.REVIEW


@pytest.mark.parametrize(
    "shared_step",
    [
        WorkflowStepKey.OPTIONS,
        WorkflowStepKey.PAYMENT,
        WorkflowStepKey.REVIEW,
        WorkflowStepKey.CONFIRMATION,
    ],
)
def test_shared_steps_without_draft_context_default_to_legacy(shared_step):
    assert get_visible_workflow(current_step=shared_step) == LEGACY_WORKFLOW


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("no", ExistingCase.NEW),
        ("yes", ExistingCase.EXISTING),
        ("responding", ExistingCase.EXISTING),
        ("unsure", ExistingCase.UNSURE),
        ("", ""),
    ],
)
def test_existing_case_values_are_normalized(value, expected):
    assert normalize_existing_case(value) == expected


def test_normalized_case_values_can_be_read_by_legacy_clients():
    assert legacy_existing_case_value(ExistingCase.NEW) == "no"
    assert legacy_existing_case_value(ExistingCase.EXISTING) == "yes"


def test_new_case_skips_lookup_and_confirmation():
    new_case = draft(existing_case=ExistingCase.NEW)

    assert WorkflowStepKey.CASE_LOOKUP not in keys(get_visible_workflow(new_case))
    assert WorkflowStepKey.CASE_CONFIRMATION not in keys(get_visible_workflow(new_case))
    assert get_next_step(WorkflowStepKey.EXTRACTION_REVIEW, new_case).key == WorkflowStepKey.DOCUMENT_CHECKLIST


def test_existing_case_uses_lookup_and_confirmation():
    existing_case = draft(existing_case=ExistingCase.EXISTING)

    assert WorkflowStepKey.CASE_LOOKUP in keys(get_visible_workflow(existing_case))
    assert WorkflowStepKey.CASE_CONFIRMATION in keys(get_visible_workflow(existing_case))
    assert get_next_step(WorkflowStepKey.EXTRACTION_REVIEW, existing_case).key == WorkflowStepKey.CASE_LOOKUP


def test_unsure_case_stays_on_extraction_review():
    unsure_case = draft(existing_case=ExistingCase.UNSURE)

    assert get_next_step(WorkflowStepKey.EXTRACTION_REVIEW, unsure_case) is None


def test_party_details_only_appear_for_incomplete_parties():
    incomplete = SimpleNamespace(first_name="Ada", last_name="", organization_name="")
    complete = SimpleNamespace(first_name="Ada", last_name="Lovelace", organization_name="")

    assert WorkflowStepKey.PARTY_DETAILS in keys(get_visible_workflow(draft(parties=[incomplete])))
    assert WorkflowStepKey.PARTY_DETAILS not in keys(get_visible_workflow(draft(parties=[complete])))


def test_case_questions_only_appear_when_required():
    assert WorkflowStepKey.CASE_QUESTIONS not in keys(get_visible_workflow(draft()))
    assert WorkflowStepKey.CASE_QUESTIONS in keys(get_visible_workflow(draft(case_questions_required=True)))


def test_get_step_raises_key_error_for_invalid_step():
    with pytest.raises(KeyError):
        get_step("invalid_step")


def test_get_step_url_reverses_an_available_route():
    expected_url = reverse("payment", kwargs={"jurisdiction": "illinois"})
    assert get_step_url(WorkflowStepKey.PAYMENT, "illinois") == expected_url


def test_resume_preserves_legacy_draft_routes():
    expected_url = reverse("upload", kwargs={"jurisdiction": "illinois"})
    assert get_resume_step_url(WorkflowStepKey.DOCUMENTS, "illinois") == expected_url


def test_resume_skips_options_for_pre_migration_drafts():
    expected_url = reverse("upload_first", kwargs={"jurisdiction": "illinois"})
    assert get_resume_step_url(WorkflowStepKey.OPTIONS, "illinois") == expected_url


def test_resume_falls_back_for_an_unrecognised_step():
    expected_url = reverse("upload_first", kwargs={"jurisdiction": "illinois"})
    assert get_resume_step_url("a_step_that_was_removed", "illinois") == expected_url


def test_resume_returns_none_without_a_draft():
    assert get_resume_step_url(None, "illinois") is None


def test_workflow_context_uses_draft_branch_and_includes_stage_progress():
    legacy_draft = draft(current_step=WorkflowStepKey.PAYMENT, workflow_version=1)
    context = get_workflow_context(WorkflowStepKey.PAYMENT, "illinois", legacy_draft)

    assert context["workflow_current_step"].key == WorkflowStepKey.PAYMENT
    assert context["workflow_previous_step"].key == WorkflowStepKey.DOCUMENTS
    assert context["workflow_next_step"].key == WorkflowStepKey.REVIEW
    assert context["workflow_previous_url"] == reverse("upload", kwargs={"jurisdiction": "illinois"})
    assert context["workflow_next_url"] == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    assert [stage.value for stage in context["workflow_stages"]] == [
        "filing",
        "upload",
        "confirm_case",
        "organize_documents",
        "fees",
        "review",
    ]
