import pytest
from django.urls import reverse

from efile.workflow import (
    FILING_WORKFLOW,
    get_next_step,
    get_previous_step,
    get_step,
    get_step_url,
    get_workflow_context,
    get_workflow_steps,
)


@pytest.mark.parametrize(
    ("step_key", "label"),
    [
        ("options", "Options"),
        ("upload_first", "Upload lead document"),
        ("case_information", "Case information"),
        ("documents", "Documents"),
        ("payment", "Payment"),
        ("review", "Review"),
        ("confirmation", "Confirmation"),
    ],
)
def test_get_step_returns_registered_step(step_key, label):
    step = get_step(step_key)

    assert step.key == step_key
    assert step.label == label


def test_get_workflow_steps_returns_ordered_workflow():
    assert get_workflow_steps() == FILING_WORKFLOW
    assert [step.key for step in get_workflow_steps()] == [
        "options",
        "upload_first",
        "case_information",
        "documents",
        "payment",
        "review",
        "confirmation",
    ]


def test_get_step_raises_key_error_for_unknown_step():
    with pytest.raises(KeyError):
        get_step("unknown")


def test_get_previous_step_returns_none_for_first_step():
    assert get_previous_step("options") is None


def test_get_previous_step_returns_prior_step():
    assert get_previous_step("case_information").key == "upload_first"


def test_get_next_step_returns_following_step():
    assert get_next_step("case_information").key == "documents"


def test_get_next_step_returns_none_for_last_step():
    assert get_next_step("confirmation") is None


def test_get_step_url_reverses_workflow_route():
    assert get_step_url("payment", "illinois") == reverse("payment", kwargs={"jurisdiction": "illinois"})


def test_get_workflow_context_includes_current_previous_and_next_urls():
    context = get_workflow_context("payment", "illinois")

    assert context["workflow_current_step"].key == "payment"
    assert context["workflow_previous_step"].key == "documents"
    assert context["workflow_next_step"].key == "review"
    assert context["workflow_previous_url"] == reverse("upload", kwargs={"jurisdiction": "illinois"})
    assert context["workflow_next_url"] == reverse("case_review", kwargs={"jurisdiction": "illinois"})
