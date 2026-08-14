from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.services.current_drafts import ensure_current_draft
from efile.services.drafts import draft_snapshot
from efile.services.people import get_case_questions, needs_amount_in_controversy, parse_question_answer
from efile.workflow import RETURN_TO_REVIEW, WorkflowStepKey, get_step_url, get_workflow_context


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


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
    show_amount_field = needs_amount_in_controversy(draft)
    if not questions and not show_amount_field:
        return_to = request.POST.get("return_to") or request.GET.get("return_to")
        next_step = WorkflowStepKey.REVIEW if return_to == RETURN_TO_REVIEW else WorkflowStepKey.PAYMENT
        draft.current_step = next_step
        draft.save(update_fields=["current_step", "updated_at"])
        return redirect(get_step_url(next_step, jurisdiction))

    for question in questions:
        raw_value = (draft.supplemental_fields or {}).get(question["name"], "")
        if question["type"] == "radio":
            raw_value = "" if raw_value in (None, "") else str(raw_value).lower()
        elif raw_value is None:
            raw_value = ""
        question["value"] = raw_value

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

        amount_in_controversy = None
        if show_amount_field:
            amount_in_controversy = _parse_amount(request.POST.get("amount_in_controversy", ""))
            if amount_in_controversy is None:
                errors.append("Amount in controversy")

        if errors:
            messages.error(request, f"Answer these questions: {', '.join(dict.fromkeys(errors))}.")
        else:
            draft.supplemental_fields = {
                **(draft.supplemental_fields or {}),
                **answers,
                "_case_questions_required": True,
            }
            update_fields = ["supplemental_fields", "current_step", "updated_at"]
            if show_amount_field:
                draft.amount_in_controversy = str(amount_in_controversy)
                update_fields.append("amount_in_controversy")
            next_step = (
                WorkflowStepKey.REVIEW if request.POST.get("return_to") == RETURN_TO_REVIEW else WorkflowStepKey.PAYMENT
            )
            draft.current_step = next_step
            draft.save(update_fields=update_fields)
            return redirect(get_step_url(next_step, jurisdiction))

    context = {
        "is_logged_in": True,
        "filing_draft": draft_snapshot(draft),
        "questions": questions,
        "answers": draft.supplemental_fields or {},
        "return_to": request.GET.get("return_to", ""),
        "show_amount_field": show_amount_field,
        "amount_in_controversy": draft.amount_in_controversy,
    }
    context.update(get_workflow_context(WorkflowStepKey.CASE_QUESTIONS, jurisdiction, draft))
    return render(request, "efile/case_questions.html", context)
