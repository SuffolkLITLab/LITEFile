"""The filer's own list of matters, reachable at any time.

A plan is made during a filing, but it is not owned by one: it is the thing a
filer comes back to between envelopes ("what else do I still need for my name
change?"). This screen is that home. It is deliberately outside the filing
workflow, so nothing here has to be finished before something else can start.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingPlan
from efile.services.filing_plans import (
    checklist_answers_from_post,
    grouped_checklist,
    link_case_to_plan,
    plan_progress,
    set_checklist_answers,
    status_choices,
)


def _plan_for(request, jurisdiction, plan_id):
    return get_object_or_404(FilingPlan, pk=plan_id, user=request.user, jurisdiction=jurisdiction)


@require_http_methods(["GET", "POST"])
def filing_plans(request, jurisdiction):
    if not request.user.is_authenticated or not get_tyler_token(request, jurisdiction):
        return redirect("efile_login", jurisdiction=jurisdiction)

    if request.method == "POST":
        action = request.POST.get("action")
        plan = _plan_for(request, jurisdiction, request.POST.get("plan_id"))

        if action == "save_progress":
            set_checklist_answers(plan, checklist_answers_from_post(request.POST, plan))
            messages.success(request, f"We saved your list for {plan.title}.")
        elif action == "rename":
            title = (request.POST.get("title") or "").strip()[:255]
            if not title:
                messages.error(request, "Give this plan a name you will recognize.")
            else:
                plan.title = title
                plan.save(update_fields=["title", "updated_at"])
                messages.success(request, "We renamed your plan.")
        elif action == "link_case":
            case_tracking_id = (request.POST.get("case_tracking_id") or "").strip()
            docket_number = (request.POST.get("docket_number") or "").strip()
            if not case_tracking_id or not docket_number:
                messages.error(request, "Choose one of your court cases to link.")
            else:
                link_case_to_plan(
                    plan,
                    case_tracking_id=case_tracking_id,
                    docket_number=docket_number,
                    case_title=request.POST.get("case_title", ""),
                    court_code=request.POST.get("court_code", ""),
                    court_name=request.POST.get("court_name", ""),
                )
                messages.success(
                    request,
                    f"{plan.title} now files into case {plan.docket_number}.",
                )
        elif action == "unlink_case":
            link_case_to_plan(plan, case_tracking_id="", docket_number="", case_title="")
            messages.success(request, f"{plan.title} is no longer linked to a court case.")

        return redirect("filing_plans", jurisdiction=jurisdiction)

    plans = [
        {
            "plan": plan,
            "progress": plan_progress(plan),
            "groups": grouped_checklist(plan),
        }
        for plan in FilingPlan.objects.filter(user=request.user, jurisdiction=jurisdiction)
    ]
    return render(
        request,
        "efile/filing_plans.html",
        {"is_logged_in": True, "plans": plans, "status_choices": status_choices()},
    )
