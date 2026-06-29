"""Central filing workflow registry.

Use FILING_WORKFLOW as the single high-level map of the filing flow.

To add a step:
1. Add a WorkflowStepKey member for the new step.
2. Add the URL route and view.
3. Add a WorkflowStep entry in the desired position below.
4. Add get_workflow_context(WorkflowStepKey.YOUR_STEP, jurisdiction) to that view's context.
5. Update any navigation copy that mentions the surrounding steps.
6. Update efile/tests/test_workflow.py.

To rearrange steps:
1. Reorder FILING_WORKFLOW.
2. Update affected labels, navigation copy, and workflow tests.

This registry is intentionally linear for now. Future branching should be added
here after the durable filing draft model exists as the workflow state source.
"""

from dataclasses import dataclass
from enum import StrEnum

from django.urls import reverse


class WorkflowStepKey(StrEnum):
    """Stable identifiers for filing workflow steps."""

    OPTIONS = "options"
    UPLOAD_FIRST = "upload_first"
    CASE_INFORMATION = "case_information"
    DOCUMENTS = "documents"
    PAYMENT = "payment"
    REVIEW = "review"
    CONFIRMATION = "confirmation"


@dataclass(frozen=True)
class WorkflowStep:
    """A single screen in the filing workflow."""

    key: WorkflowStepKey
    label: str
    url_name: str


FILING_WORKFLOW: tuple[WorkflowStep, ...] = (
    WorkflowStep(WorkflowStepKey.OPTIONS, "Options", "efile_options"),
    WorkflowStep(WorkflowStepKey.UPLOAD_FIRST, "Upload lead document", "upload_first"),
    WorkflowStep(WorkflowStepKey.CASE_INFORMATION, "Case information", "expert_form"),
    WorkflowStep(WorkflowStepKey.DOCUMENTS, "Documents", "upload"),
    WorkflowStep(WorkflowStepKey.PAYMENT, "Payment", "payment"),
    WorkflowStep(WorkflowStepKey.REVIEW, "Review", "case_review"),
    WorkflowStep(WorkflowStepKey.CONFIRMATION, "Confirmation", "filing_confirmation"),
)


def get_workflow_steps() -> tuple[WorkflowStep, ...]:
    return FILING_WORKFLOW


def get_step(step_key: WorkflowStepKey | str) -> WorkflowStep:
    try:
        return next(step for step in FILING_WORKFLOW if step.key == step_key)
    except StopIteration as exc:
        raise KeyError(f"Unknown workflow step: {step_key}") from exc


def get_step_index(step_key: WorkflowStepKey | str) -> int:
    for index, step in enumerate(FILING_WORKFLOW):
        if step.key == step_key:
            return index
    raise KeyError(f"Unknown workflow step: {step_key}")


def get_previous_step(step_key: WorkflowStepKey | str) -> WorkflowStep | None:
    index = get_step_index(step_key)
    if index == 0:
        return None
    return FILING_WORKFLOW[index - 1]


def get_next_step(step_key: WorkflowStepKey | str) -> WorkflowStep | None:
    index = get_step_index(step_key)
    try:
        return FILING_WORKFLOW[index + 1]
    except IndexError:
        return None


def get_step_url(step_key: WorkflowStepKey | str, jurisdiction: str) -> str:
    step = get_step(step_key)
    return reverse(step.url_name, kwargs={"jurisdiction": jurisdiction})


def get_workflow_context(current_step: WorkflowStepKey | str, jurisdiction: str) -> dict:
    previous_step = get_previous_step(current_step)
    next_step = get_next_step(current_step)
    previous_url = None
    next_url = None

    if previous_step:
        previous_url = get_step_url(previous_step.key, jurisdiction)
    if next_step:
        next_url = get_step_url(next_step.key, jurisdiction)

    return {
        "workflow_steps": get_workflow_steps(),
        "workflow_current_step": get_step(current_step),
        "workflow_previous_step": previous_step,
        "workflow_next_step": next_step,
        "workflow_previous_url": previous_url,
        "workflow_next_url": next_url,
    }
