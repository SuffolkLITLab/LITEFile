from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.people import get_case_questions, parse_question_answer
from efile.workflow import WorkflowStepKey, get_step_url, get_workflow_context


@require_http_methods(["GET", "POST"])
def case_questions(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    draft = ensure_current_draft(
        request,
        jurisdiction,
        current_step=WorkflowStepKey.CASE_QUESTIONS,
        workflow_version=2,
    )
    questions = get_case_questions(draft)
    if not questions:
        draft.current_step = WorkflowStepKey.PAYMENT
        draft.save(update_fields=["current_step", "updated_at"])
        return redirect(get_step_url(WorkflowStepKey.PAYMENT, jurisdiction))

    for question in questions:
        question["value"] = (draft.supplemental_fields or {}).get(question["name"], "")

    if request.method == "POST":
        answers = {}
        errors = []
        for question in questions:
            value = request.POST.get(question["name"], "")
            if question["name"] == "child_count" and request.POST.get("has_children") == "false":
                value = ""
            if question["required"] and value == "" and question["name"] != "child_count":
                errors.append(question["label"])
                continue
            try:
                answers[question["name"]] = parse_question_answer(question, value)
            except ValueError:
                errors.append(question["label"])
        if request.POST.get("has_children") == "true" and not request.POST.get("child_count"):
            errors.append("Number of minor children")
        if errors:
            messages.error(request, f"Answer these questions: {', '.join(dict.fromkeys(errors))}.")
        else:
            draft.supplemental_fields = {
                **(draft.supplemental_fields or {}),
                **answers,
                "_case_questions_required": True,
            }
            draft.current_step = WorkflowStepKey.PAYMENT
            draft.save(update_fields=["supplemental_fields", "current_step", "updated_at"])
            return redirect(get_step_url(WorkflowStepKey.PAYMENT, jurisdiction))

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "questions": questions,
        "answers": draft.supplemental_fields or {},
    }
    context.update(get_workflow_context(WorkflowStepKey.CASE_QUESTIONS, jurisdiction, draft))
    return render(request, "efile/case_questions.html", context)
