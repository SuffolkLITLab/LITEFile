"""Bridge helpers for moving the current session-backed flow to durable drafts."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from django.db import transaction

from efile.models import FilingDocument, FilingDraft, FilingParty


CASE_FIELD_MAPPINGS: dict[str, tuple[str, ...]] = {
    "existing_case": ("existing_case",),
    "court_code": ("court_code", "court"),
    "court_name": ("court_name",),
    "case_category_code": ("case_category_code", "case_category"),
    "case_category_name": ("case_category_name",),
    "case_type_code": ("case_type_code", "case_type"),
    "case_type_name": ("case_type_name",),
    "case_subtype_code": ("case_subtype_code", "case_subtype"),
    "case_subtype_name": ("case_subtype_name",),
    "filing_type_code": ("filing_type_code", "filing_type", "filing_type_id"),
    "filing_type_name": ("filing_type_name",),
    "document_type_code": ("document_type_code", "document_type"),
    "document_type_name": ("document_type_name",),
    "previous_case_id": ("previous_case_id", "case_tracking_id"),
    "docket_number": ("docket_number", "case_docket_id"),
    "selected_payment_account_id": ("selected_payment_account_id", "selected_payment_account", "payment_account_id"),
    "selected_payment_account_name": ("selected_payment_account_name", "payment_account_name"),
}


def first_value(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""


def as_string(value: Any) -> str:
    return "" if value in (None, "") else str(value)


def authenticated_user(request):
    user = getattr(request, "user", None)
    return user if getattr(user, "is_authenticated", False) else None


def ensure_session_key(request) -> str:
    if not getattr(request.session, "session_key", None):
        request.session.create()
    return request.session.session_key or ""


def get_active_draft(request) -> FilingDraft | None:
    draft_id = request.session.get("filing_draft_id")
    if draft_id:
        try:
            return FilingDraft.objects.get(pk=draft_id)
        except FilingDraft.DoesNotExist:
            request.session.pop("filing_draft_id", None)
            request.session.modified = True

    user = authenticated_user(request)
    if user:
        draft = (
            FilingDraft.objects.filter(user=user, status__in=[FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR])
            .order_by("-updated_at")
            .first()
        )
        if draft:
            request.session["filing_draft_id"] = draft.pk
            request.session.modified = True
            return draft

    session_key = getattr(request.session, "session_key", None)
    if session_key:
        draft = (
            FilingDraft.objects.filter(session_key=session_key, status__in=[FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR])
            .order_by("-updated_at")
            .first()
        )
        if draft:
            request.session["filing_draft_id"] = draft.pk
            request.session.modified = True
            return draft

    return None


@transaction.atomic
def create_draft(request, jurisdiction: str, *, current_step: str = FilingDraft.WorkflowStep.OPTIONS) -> FilingDraft:
    session_key = ensure_session_key(request)
    session_id = request.session.get("session_id") or str(uuid.uuid4())
    request.session["session_id"] = session_id
    request.session["jurisdiction"] = jurisdiction

    draft = FilingDraft.objects.create(
        user=authenticated_user(request),
        session_key=session_key,
        session_id=session_id,
        jurisdiction=jurisdiction,
        current_step=str(current_step),
    )
    request.session["filing_draft_id"] = draft.pk
    request.session.modified = True
    return draft


@transaction.atomic
def ensure_draft(request, jurisdiction: str | None = None, *, current_step: str | None = None) -> FilingDraft:
    draft = get_active_draft(request)
    if draft is None:
        return create_draft(
            request,
            jurisdiction or request.session.get("jurisdiction") or "",
            current_step=current_step or FilingDraft.WorkflowStep.OPTIONS,
        )

    update_fields = []
    if jurisdiction and draft.jurisdiction != jurisdiction:
        draft.jurisdiction = jurisdiction
        update_fields.append("jurisdiction")
    if current_step and draft.current_step != str(current_step):
        draft.current_step = str(current_step)
        update_fields.append("current_step")
    if update_fields:
        update_fields.append("updated_at")
        draft.save(update_fields=update_fields)

    request.session["filing_draft_id"] = draft.pk
    request.session.modified = True
    return draft


@transaction.atomic
def update_draft_from_case_data(
    draft: FilingDraft,
    case_data: Mapping[str, Any] | None,
    *,
    current_step: str | None = None,
) -> FilingDraft:
    data = dict(case_data or {})
    update_fields = []

    for draft_field, source_keys in CASE_FIELD_MAPPINGS.items():
        value = as_string(first_value(data, *source_keys))
        if getattr(draft, draft_field) != value:
            setattr(draft, draft_field, value)
            update_fields.append(draft_field)

    optional_services = data.get("optional_services") or []
    if draft.optional_services != optional_services:
        draft.optional_services = optional_services
        update_fields.append("optional_services")

    if draft.extra_case_data != data:
        draft.extra_case_data = data
        update_fields.append("extra_case_data")

    if current_step and draft.current_step != str(current_step):
        draft.current_step = str(current_step)
        update_fields.append("current_step")

    if update_fields:
        update_fields.append("updated_at")
        draft.save(update_fields=sorted(set(update_fields)))

    sync_parties_from_case_data(draft, data)
    return draft


@transaction.atomic
def sync_documents_from_upload_data(
    draft: FilingDraft,
    upload_data: Mapping[str, Any] | None,
    *,
    current_step: str | None = None,
) -> FilingDraft:
    data = dict(upload_data or {})
    files = dict(data.get("files") or {})
    lead_document = files.get("lead")
    if lead_document:
        upsert_document(draft, FilingDocument.Role.LEAD, lead_document, data, sort_order=0)

    supporting_documents = files.get("supporting") or []
    supporting_configs = data.get("supporting_documents") or []
    kept_orders = []
    for index, document in enumerate(supporting_documents):
        config = supporting_configs[index] if index < len(supporting_configs) else {}
        upsert_document(draft, FilingDocument.Role.SUPPORTING, document, config, sort_order=index)
        kept_orders.append(index)

    if kept_orders:
        FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.SUPPORTING).exclude(sort_order__in=kept_orders).delete()
    else:
        FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.SUPPORTING).delete()

    guesses = data.get("guesses") or {}
    update_fields = []
    if guesses and draft.extracted_guesses != guesses:
        draft.extracted_guesses = guesses
        update_fields.append("extracted_guesses")
    if current_step and draft.current_step != str(current_step):
        draft.current_step = str(current_step)
        update_fields.append("current_step")
    if update_fields:
        update_fields.append("updated_at")
        draft.save(update_fields=update_fields)

    return draft


def sync_parties_from_case_data(draft: FilingDraft, case_data: Mapping[str, Any]) -> None:
    petitioner = {
        "party_type": as_string(first_value(case_data, "petitioner_party_type", "party_type", "determined_party_type")),
        "first_name": as_string(first_value(case_data, "petitioner_first_name", "first_name")),
        "last_name": as_string(first_value(case_data, "petitioner_last_name", "last_name")),
        "email": as_string(first_value(case_data, "petitioner_email", "email")),
        "phone": as_string(first_value(case_data, "petitioner_phone", "phone")),
        "address_line_1": as_string(first_value(case_data, "petitioner_address", "address", "address_line_1")),
        "metadata": {key: value for key, value in case_data.items() if key.startswith("petitioner_")},
    }
    if any(petitioner.get(key) for key in ("party_type", "first_name", "last_name", "email")):
        FilingParty.objects.update_or_create(draft=draft, role="petitioner", sort_order=0, defaults=petitioner)

    name_sought = {
        "party_type": as_string(first_value(case_data, "new_name_party_type")),
        "first_name": as_string(first_value(case_data, "new_first_name")),
        "middle_name": as_string(first_value(case_data, "new_middle_name")),
        "last_name": as_string(first_value(case_data, "new_last_name")),
        "suffix": as_string(first_value(case_data, "new_suffix")),
        "metadata": {key: value for key, value in case_data.items() if key.startswith("new_") or key.startswith("reason_")},
    }
    if any(name_sought.get(key) for key in ("party_type", "first_name", "last_name")):
        FilingParty.objects.update_or_create(draft=draft, role="name_sought", sort_order=0, defaults=name_sought)


def upsert_document(
    draft: FilingDraft,
    role: str,
    document: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    sort_order: int,
) -> FilingDocument:
    document_data = dict(document or {})
    config_data = dict(config or {})
    defaults = {
        "name": as_string(first_value(document_data, "name", "filename", "original_filename")),
        "original_filename": as_string(first_value(document_data, "original_filename", "filename", "name")),
        "size": positive_int(first_value(document_data, "size", "file_size")),
        "content_type": as_string(first_value(document_data, "content_type", "mime_type", "type")),
        "s3_key": as_string(first_value(document_data, "s3_key", "key")),
        "public_url": as_string(first_value(document_data, "url", "s3_url", "file_url", "download_url")),
        "filing_type_code": as_string(first_value(config_data, "filing_type", "lead_filing_type", "filing_type_code")),
        "filing_type_name": as_string(first_value(config_data, "filing_type_name", "lead_filing_type_name")),
        "document_type_code": as_string(first_value(config_data, "document_type", "lead_document_type", "document_type_code")),
        "document_type_name": as_string(first_value(config_data, "document_type_name", "lead_document_type_name")),
        "filing_component_code": as_string(first_value(config_data, "filing_component", "lead_filing_component", "filing_component_code")),
        "filing_component_name": as_string(first_value(config_data, "filing_component_name", "lead_filing_component_name")),
        "courtesy_copy_email": as_string(first_value(config_data, "cc_email", "lead_cc_email")),
        "metadata": {"file": document_data, "config": config_data},
    }
    document, _created = FilingDocument.objects.update_or_create(
        draft=draft,
        role=role,
        sort_order=sort_order,
        defaults=defaults,
    )
    return document


def draft_snapshot(draft: FilingDraft | None) -> dict[str, Any] | None:
    if draft is None:
        return None
    return {
        "id": draft.pk,
        "jurisdiction": draft.jurisdiction,
        "status": draft.status,
        "current_step": draft.current_step,
        "existing_case": draft.existing_case,
        "court_code": draft.court_code,
        "court_name": draft.court_name,
        "case_category_code": draft.case_category_code,
        "case_category_name": draft.case_category_name,
        "case_type_code": draft.case_type_code,
        "case_type_name": draft.case_type_name,
        "filing_type_code": draft.filing_type_code,
        "filing_type_name": draft.filing_type_name,
        "document_type_code": draft.document_type_code,
        "document_type_name": draft.document_type_name,
        "previous_case_id": draft.previous_case_id,
        "docket_number": draft.docket_number,
        "selected_payment_account_id": draft.selected_payment_account_id,
        "selected_payment_account_name": draft.selected_payment_account_name,
        "optional_services": draft.optional_services,
        "extracted_guesses": draft.extracted_guesses,
        "document_count": draft.documents.count(),
        "party_count": draft.parties.count(),
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
        "submitted_at": draft.submitted_at.isoformat() if draft.submitted_at else None,
    }


def positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None
