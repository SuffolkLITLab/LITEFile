from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class WorkflowStep:
    """A single screen in the filing workflow."""

    key: str
    label: str
    url_name: str


FILING_WORKFLOW: tuple[WorkflowStep, ...] = (
    WorkflowStep("options", "Options", "efile_options"),
    WorkflowStep("upload_first", "Upload lead document", "upload_first"),
    WorkflowStep("case_information", "Case information", "expert_form"),
    WorkflowStep("documents", "Documents", "upload"),
    WorkflowStep("payment", "Payment", "payment"),
    WorkflowStep("review", "Review", "case_review"),
    WorkflowStep("confirmation", "Confirmation", "filing_confirmation"),
)


def get_workflow_steps() -> tuple[WorkflowStep, ...]:
    return FILING_WORKFLOW


def get_step(step_key: str) -> WorkflowStep:
    try:
        return next(step for step in FILING_WORKFLOW if step.key == step_key)
    except StopIteration as exc:
        raise KeyError(f"Unknown workflow step: {step_key}") from exc


def get_step_index(step_key: str) -> int:
    for index, step in enumerate(FILING_WORKFLOW):
        if step.key == step_key:
            return index
    raise KeyError(f"Unknown workflow step: {step_key}")


def get_previous_step(step_key: str) -> WorkflowStep | None:
    index = get_step_index(step_key)
    if index == 0:
        return None
    return FILING_WORKFLOW[index - 1]


def get_next_step(step_key: str) -> WorkflowStep | None:
    index = get_step_index(step_key)
    try:
        return FILING_WORKFLOW[index + 1]
    except IndexError:
        return None


def get_step_url(step_key: str, jurisdiction: str) -> str:
    step = get_step(step_key)
    return reverse(step.url_name, kwargs={"jurisdiction": jurisdiction})


def get_workflow_context(current_step: str, jurisdiction: str) -> dict:
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
