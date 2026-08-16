"""Create and maintain a filer's FilingPlan -- the matter behind their filings.

A plan is the filer's own list of documents for a matter ("my name change"),
kept across however many envelopes that matter takes. Two ideas matter here:

* The plan stores names, not court codes. When the filer starts another filing
  from the plan, the stored names are resolved against the court's *current*
  code lists, so a plan made six months ago still works after the court renumbers
  everything.
* The checklist is snapshotted into the plan when it is created. Later edits to
  partner YAML change what new plans get, and leave existing plans alone.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from django.db import transaction

from efile.models import FilingDocument, FilingDraft, FilingPlan
from efile.services.document_checklists import (
    REQUIREMENT_LABELS,
    REQUIREMENT_ORDER,
    normalize_name,
    resolve_document_checklist,
)
from efile.services.drafts import create_draft
from efile.workflow import WorkflowStepKey

logger = logging.getLogger(__name__)

DEFAULT_PLAN_TITLE = "My filing"


def lead_filing_type_name(draft: FilingDraft) -> str:
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    return (lead.filing_type_name if lead else "") or ""


def plan_title_for(draft: FilingDraft) -> str:
    """Name a new plan after the case it gathers documents for."""

    for candidate in (draft.case_type_name, draft.case_category_name, draft.case_title):
        if candidate:
            return candidate[:255]
    return DEFAULT_PLAN_TITLE


def checklist_snapshot(
    checklist: dict[str, dict[str, Any]],
    previous: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Copy resolved guidance into plan shape, keeping any progress already made."""

    previous = previous or {}
    snapshot: dict[str, dict[str, Any]] = {}
    for item_id, item in checklist.items():
        was_complete = bool((previous.get(item_id) or {}).get("complete"))
        snapshot[item_id] = {**item, "complete": was_complete}
    return snapshot


def resolve_checklist_for_draft(draft: FilingDraft) -> dict[str, dict[str, Any]]:
    return resolve_document_checklist(
        jurisdiction=draft.jurisdiction,
        court_code=draft.court_code,
        case_category_name=draft.case_category_name,
        case_type_name=draft.case_type_name,
        lead_filing_type_name=lead_filing_type_name(draft),
    )


def _plan_case(plan: FilingPlan) -> tuple[str, str, str, str]:
    return (plan.court_code, plan.case_category_name, plan.case_type_name, plan.lead_filing_type_name)


def _draft_case(draft: FilingDraft) -> tuple[str, str, str, str]:
    return (
        draft.court_code,
        draft.case_category_name,
        draft.case_type_name,
        lead_filing_type_name(draft),
    )


def _detach(draft: FilingDraft) -> None:
    draft.plan = None
    draft.save(update_fields=["plan", "updated_at"])


def _refresh_plan(plan: FilingPlan, draft: FilingDraft) -> FilingPlan | None:
    """Move a plan onto the case its only filing has become.

    Someone who goes back and picks a different case type is not gathering
    documents for the old one any more. Progress on items that survive the
    change is kept; guidance for a case they are no longer filing is not.
    """

    checklist = resolve_checklist_for_draft(draft)
    if not checklist:
        _detach(draft)
        return None

    auto_title = plan.case_type_name or plan.case_category_name or DEFAULT_PLAN_TITLE
    if plan.title == auto_title:
        plan.title = plan_title_for(draft)
    plan.court_code = draft.court_code
    plan.court_name = draft.court_name
    plan.case_category_name = draft.case_category_name
    plan.case_type_name = draft.case_type_name
    plan.lead_filing_type_name = lead_filing_type_name(draft)
    plan.checklist = checklist_snapshot(checklist, plan.checklist)
    plan.save()
    return plan


@transaction.atomic
def ensure_plan_for_draft(draft: FilingDraft) -> FilingPlan | None:
    """Attach a plan to this draft, creating one from the configured checklist.

    Returns ``None`` when no partner checklist covers this case, so an
    unconfigured case type leaves the filer's experience exactly as it was.
    """

    plan = draft.plan
    if plan is not None:
        if _plan_case(plan) == _draft_case(draft):
            return plan
        if not FilingDraft.objects.filter(plan=plan).exclude(pk=draft.pk).exists():
            return _refresh_plan(plan, draft)
        # The matter has other filings behind it, so it keeps the case it was
        # made for. This filing has become a different one and needs its own plan.
        _detach(draft)

    checklist = resolve_checklist_for_draft(draft)
    if not checklist:
        return None

    plan = FilingPlan.objects.create(
        user=draft.user,
        title=plan_title_for(draft),
        jurisdiction=draft.jurisdiction,
        court_code=draft.court_code,
        court_name=draft.court_name,
        case_category_name=draft.case_category_name,
        case_type_name=draft.case_type_name,
        lead_filing_type_name=lead_filing_type_name(draft),
        checklist=checklist_snapshot(checklist),
    )
    draft.plan = plan
    draft.save(update_fields=["plan", "updated_at"])
    return plan


def set_checklist_progress(plan: FilingPlan, completed_ids) -> FilingPlan:
    """Record which items the filer says they have gathered.

    Only items already in the plan can be ticked: the checkboxes come from the
    plan's own snapshot, so anything else in the POST is not ours.
    """

    completed = {str(item_id) for item_id in completed_ids}
    checklist = dict(plan.checklist or {})
    for item_id, item in checklist.items():
        if isinstance(item, dict):
            item["complete"] = item_id in completed
    plan.checklist = checklist
    plan.save(update_fields=["checklist", "updated_at"])
    return plan


def grouped_checklist(plan: FilingPlan | None) -> list[dict[str, Any]]:
    """Shape a plan's checklist for the page: one group per requirement level."""

    if plan is None:
        return []

    groups: dict[str, list[dict[str, Any]]] = {level: [] for level in REQUIREMENT_ORDER}
    for item_id, item in (plan.checklist or {}).items():
        if not isinstance(item, dict):
            continue
        requirement = item.get("requirement", "")
        if requirement not in groups:
            continue
        groups[requirement].append(
            {
                "id": item_id,
                "label": item.get("label") or item_id,
                "description": item.get("description", ""),
                "complete": bool(item.get("complete")),
            }
        )

    return [
        {"requirement": level, "label": REQUIREMENT_LABELS[level], "items": items}
        for level, items in groups.items()
        if items
    ]


# --- Starting another filing from a saved plan ------------------------------
#
# The plan remembers names. Tyler remembers codes, and changes them. Everything
# below turns the first into the second, at the moment of filing.


def _codes(jurisdiction: str, path: str, **params: Any) -> list[dict[str, Any]]:
    url = f"{settings.EFSP_URL}/jurisdictions/{jurisdiction}/codes/courts/{path}"
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Could not load %s for jurisdiction %s", url, jurisdiction)
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _code_for_name(options: list[dict[str, Any]], name: str) -> str:
    wanted = normalize_name(name)
    if not wanted:
        return ""
    for option in options:
        if normalize_name(option.get("name")) == wanted:
            return str(option.get("code") or "")
    return ""


def resolve_plan_case_codes(plan: FilingPlan) -> dict[str, str]:
    """Look up today's codes for the names a plan saved.

    Anything the court no longer publishes under that name comes back empty, and
    the filer picks it again on the confirm-filing step -- which is the honest
    outcome, and much better than filing against a stale code.
    """

    codes = {"case_category_code": "", "case_type_code": "", "lead_filing_type_code": ""}
    if not plan.court_code:
        return codes

    categories = _codes(
        plan.jurisdiction,
        f"{plan.court_code}/categories",
        fileable_only=True,
        timing="Initial",
    )
    codes["case_category_code"] = _code_for_name(categories, plan.case_category_name)
    if not codes["case_category_code"]:
        return codes

    case_types = _codes(
        plan.jurisdiction,
        f"{plan.court_code}/case_types/",
        category_id=codes["case_category_code"],
        timing="Initial",
    )
    codes["case_type_code"] = _code_for_name(case_types, plan.case_type_name)
    if not codes["case_type_code"] or not plan.lead_filing_type_name:
        return codes

    filing_types = _codes(
        plan.jurisdiction,
        f"{plan.court_code}/filing_types/",
        initial="true",
        category_id=codes["case_category_code"],
        type_id=codes["case_type_code"],
    )
    codes["lead_filing_type_code"] = _code_for_name(filing_types, plan.lead_filing_type_name)
    return codes


@transaction.atomic
def create_draft_from_plan(user, plan: FilingPlan) -> FilingDraft:
    """Start another filing in an existing matter, using today's court codes."""

    codes = resolve_plan_case_codes(plan)
    draft = create_draft(
        user=user,
        jurisdiction=plan.jurisdiction,
        current_step=WorkflowStepKey.UPLOAD_DOCUMENTS,
    )
    draft.plan = plan
    # Whether this one opens a new case or joins the case the plan's first filing
    # started is the filer's answer to give, on the confirm-filing step.
    draft.court_code = plan.court_code
    draft.court_name = plan.court_name
    draft.case_category_name = plan.case_category_name
    draft.case_category_code = codes["case_category_code"]
    draft.case_type_name = plan.case_type_name
    draft.case_type_code = codes["case_type_code"]
    draft.save()
    return draft
