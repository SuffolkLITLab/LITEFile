"""Deployment-owned restrictions on filing through LITEFile, matched by API codes."""

from django.shortcuts import render
from django.utils.translation import gettext as _

from efile.models import FilingDocument
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase, WorkflowStepKey, get_step_url, get_workflow_context


def filing_unavailable_message(jurisdiction, court, *, case_category="", case_type="", filing_types=()):
    """Return a reason, or an empty string when no restriction matches.

    Exact court settings are checked before a county prefix (``cook:*``).
    Rules are additive: an exact court cannot enable a county-wide restriction.
    Values within a selector are alternatives; selectors within a rule must all
    match. Names from the browser never participate in an availability decision.
    """
    courts = config_loader.load_jurisdiction_config(jurisdiction).get("court_specific_requirements") or {}
    keys = [court]
    if ":" in court:
        keys.append(court.split(":", 1)[0] + ":*")
    selections = {
        "case_categories": {str(case_category)} - {""},
        "case_types": {str(case_type)} - {""},
        "filing_types": {str(value) for value in filing_types if value},
    }
    for key in keys:
        availability = (courts.get(key) or {}).get("filing_availability") or {}
        fallback = availability.get("message") or _(
            "LITEFile cannot submit this filing to this court right now. Contact the court clerk to ask how to file."
        )
        # Specific explanations take precedence over the court's generic one.
        for rule in availability.get("rules") or []:
            selectors = [name for name in selections if name in rule]
            if selectors and all(
                selections[name].intersection(str(value) for value in rule[name]) for name in selectors
            ):
                return rule.get("message") or fallback
        if availability.get("enabled") is False:
            return fallback
    return ""


def draft_unavailable_message(draft):
    return filing_unavailable_message(
        draft.jurisdiction,
        draft.court_code,
        case_category=draft.case_category_code,
        case_type=draft.case_type_code,
        filing_types=FilingDocument.objects.filter(draft=draft).values_list("filing_type_code", flat=True),
    )


def unavailable_response(request, draft, message):
    """Keep the draft intact and offer corrections without suggesting a false court."""
    case_step = (
        WorkflowStepKey.CASE_LOOKUP
        if draft.existing_case == ExistingCase.EXISTING
        else WorkflowStepKey.EXTRACTION_REVIEW
    )
    context = {
        "is_logged_in": True,
        "draft": draft,
        "availability_message": message,
        "change_case_url": get_step_url(case_step, draft.jurisdiction),
        "change_documents_url": get_step_url(WorkflowStepKey.ORGANIZE_DOCUMENTS, draft.jurisdiction),
    }
    context.update(get_workflow_context(draft.current_step, draft.jurisdiction, draft))
    return render(request, "efile/filing_unavailable.html", context, status=403)
