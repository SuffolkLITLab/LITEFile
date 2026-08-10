from django.contrib import messages
from django.shortcuts import redirect

from efile.services.current_drafts import get_current_draft
from efile.workflow import WorkflowStepKey, get_resume_step_url, get_step_url


def legacy_workflow_redirect(request, jurisdiction, destination=None):
    """Send old workflow URLs forward without restoring retired screens."""

    draft = get_current_draft(request, jurisdiction=jurisdiction)
    if draft is None:
        return redirect("efile_options", jurisdiction=jurisdiction)

    if draft.workflow_version != 2:
        draft.workflow_version = 2
        draft.save(update_fields=["workflow_version", "updated_at"])

    target = {
        "upload_first": WorkflowStepKey.UPLOAD_DOCUMENTS,
        "expert_form": WorkflowStepKey.EXTRACTION_REVIEW,
        "upload": WorkflowStepKey.ORGANIZE_DOCUMENTS,
    }.get(destination)
    url = get_step_url(target, jurisdiction) if target else get_resume_step_url(draft.current_step, jurisdiction)
    messages.info(request, "This filing now uses the updated filing screens.")
    return redirect(url or get_step_url(WorkflowStepKey.FILING_PATH, jurisdiction))
