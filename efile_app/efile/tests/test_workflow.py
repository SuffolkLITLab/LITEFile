from django.urls import reverse
import pytest

from efile.workflow import (
    FILING_WORKFLOW,
    WorkflowStepKey,
    get_next_step,
    get_previous_step,
    get_step,
    get_step_url,
    get_workflow_context,
    get_workflow_steps,
)


EXPECTED_WORKFLOW_KEYS = [
    WorkflowStepKey.OPTIONS,
    WorkflowStepKey.UPLOAD_FIRST,
    WorkflowStepKey.CASE_INFORMATION,
    WorkflowStepKey.DOCUMENTS,
    WorkflowStepKey.PAYMENT,
    WorkflowStepKey.REVIEW,
    WorkflowStepKey.CONFIRMATION,
]


@pytest.mark.parametrize(
    ("step_key", "label"),
    [
        (WorkflowStepKey.OPTIONS, "Options"),
        (WorkflowStepKey.UPLOAD_FIRST, "Upload lead document"),
        (WorkflowStepKey.CASE_INFORMATION, "Case information"),
        (WorkflowStepKey.DOCUMENTS, "Documents"),
        (WorkflowStepKey.PAYMENT, "Payment"),
        (WorkflowStepKey.REVIEW, "Review"),
        (WorkflowStepKey.CONFIRMATION, "Confirmation"),
    ],
)
def test_get_step_returns_registered_step(step_key, label):
    step = get_step(step_key)

    assert step.key == step_key
    assert step.label == label


def test_get_workflow_steps_returns_ordered_workflow():
    assert get_workflow_steps() == FILING_WORKFLOW
    assert [step.key for step in get_workflow_steps()] == EXPECTED_WORKFLOW_KEYS


def test_get_step_raises_key_error_for_invalid_step():
    with pytest.raises(KeyError):
        get_step("invalid_step")


def test_get_previous_step_returns_none_for_first_step():
    assert get_previous_step(WorkflowStepKey.OPTIONS) is None


def test_get_previous_step_returns_prior_step():
    previous_step = get_previous_step(WorkflowStepKey.CASE_INFORMATION)

    assert previous_step.key == WorkflowStepKey.UPLOAD_FIRST


def test_get_next_step_returns_following_step():
    next_step = get_next_step(WorkflowStepKey.CASE_INFORMATION)

    assert next_step.key == WorkflowStepKey.DOCUMENTS


def test_get_next_step_returns_none_for_last_step():
    assert get_next_step(WorkflowStepKey.CONFIRMATION) is None


def test_get_step_url_reverses_workflow_route():
    expected_url = reverse("payment", kwargs={"jurisdiction": "illinois"})

    assert get_step_url(WorkflowStepKey.PAYMENT, "illinois") == expected_url


def test_get_workflow_context_includes_current_previous_and_next_urls():
    context = get_workflow_context(WorkflowStepKey.PAYMENT, "illinois")
    previous_url = reverse("upload", kwargs={"jurisdiction": "illinois"})
    next_url = reverse("case_review", kwargs={"jurisdiction": "illinois"})

    assert context["workflow_current_step"].key == WorkflowStepKey.PAYMENT
    assert context["workflow_previous_step"].key == WorkflowStepKey.DOCUMENTS
    assert context["workflow_next_step"].key == WorkflowStepKey.REVIEW
    assert context["workflow_previous_url"] == previous_url
    assert context["workflow_next_url"] == next_url
