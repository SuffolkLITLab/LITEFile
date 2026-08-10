from django.shortcuts import redirect

from efile.services.current_drafts import get_current_draft


def legacy_workflow_redirect(request, jurisdiction, destination):
    """Temporary bridges replaced screen-by-screen by the stacked migration."""

    draft = get_current_draft(request, jurisdiction=jurisdiction)
    if draft is not None and draft.workflow_version != 1:
        draft.workflow_version = 1
        draft.save(update_fields=["workflow_version", "updated_at"])

    route = {
        "case_lookup": "expert_form",
        "case_confirmation": "expert_form",
        "document_checklist": "expert_form",
        "organize_documents": "upload",
        "your_information": "expert_form",
        "parties": "expert_form",
        "party_details": "expert_form",
        "case_questions": "expert_form",
    }[destination]
    return redirect(route, jurisdiction=jurisdiction)
