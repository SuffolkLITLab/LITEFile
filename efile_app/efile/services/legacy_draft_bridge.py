"""Translate legacy session blobs into the durable filing draft aggregate.

Only the session-backed endpoints should import this module. It can be removed
once those endpoints write typed draft fields directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db import transaction

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.current_drafts import get_current_draft
from efile.workflow import WorkflowStepKey

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
    "selected_payment_account_id": (
        "selected_payment_account_id",
        "selected_payment_account",
        "payment_account_id",
    ),
    "selected_payment_account_name": ("selected_payment_account_name", "payment_account_name"),
}

_MISSING = object()


def _first_present(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return _MISSING


def _first_value(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""


def _as_string(value: Any) -> str:
    return "" if value in (None, "") else str(value)


@transaction.atomic
def update_draft_from_case_data(
    draft: FilingDraft,
    case_data: Mapping[str, Any] | None,
    *,
    current_step: WorkflowStepKey | str | None = None,
) -> FilingDraft:
    """Mirror one complete legacy ``case_data`` blob into ``draft``."""

    data = dict(case_data or {})
    update_fields = []

    for draft_field, source_keys in CASE_FIELD_MAPPINGS.items():
        source_value = _first_present(data, *source_keys)
        if source_value is _MISSING:
            continue
        value = _as_string(source_value)
        if getattr(draft, draft_field) != value:
            setattr(draft, draft_field, value)
            update_fields.append(draft_field)

    if "optional_services" in data:
        optional_services = data.get("optional_services") or []
        if draft.optional_services != optional_services:
            draft.optional_services = optional_services
            update_fields.append("optional_services")

    if draft.extra_case_data != data:
        draft.extra_case_data = data
        update_fields.append("extra_case_data")

    if current_step is not None and draft.current_step != str(current_step):
        draft.current_step = str(current_step)
        update_fields.append("current_step")

    if update_fields:
        draft.save(update_fields=sorted({*update_fields, "updated_at"}))

    _sync_parties_from_case_data(draft, data)
    return draft


@transaction.atomic
def sync_documents_from_upload_data(
    draft: FilingDraft,
    upload_data: Mapping[str, Any] | None,
    *,
    current_step: WorkflowStepKey | str | None = None,
) -> FilingDraft:
    """Mirror one complete legacy ``upload_data`` blob into ``draft``."""

    data = dict(upload_data or {})
    files = dict(data.get("files") or {})
    lead_document = files.get("lead")
    if lead_document:
        _upsert_document(draft, FilingDocument.Role.LEAD, lead_document, data, sort_order=0)
    else:
        FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).delete()

    supporting_documents = files.get("supporting") or []
    supporting_configs = data.get("supporting_documents") or []
    kept_orders = []
    for index, document in enumerate(supporting_documents):
        config = supporting_configs[index] if index < len(supporting_configs) else {}
        _upsert_document(draft, FilingDocument.Role.SUPPORTING, document, config, sort_order=index)
        kept_orders.append(index)

    supporting = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.SUPPORTING)
    if kept_orders:
        supporting.exclude(sort_order__in=kept_orders).delete()
    else:
        supporting.delete()

    guesses = data.get("guesses") or {}
    update_fields = []
    if draft.extracted_guesses != guesses:
        draft.extracted_guesses = guesses
        update_fields.append("extracted_guesses")
    if current_step is not None and draft.current_step != str(current_step):
        draft.current_step = str(current_step)
        update_fields.append("current_step")
    draft.save(update_fields=[*update_fields, "updated_at"])

    return draft


def sync_current_draft_case_data(request, case_data: Mapping[str, Any]) -> FilingDraft | None:
    """Compatibility hook for a session endpoint that just saved case data."""

    jurisdiction = _as_string(
        _first_value(case_data, "jurisdiction_id", "jurisdiction") or request.session.get("jurisdiction")
    )
    draft = get_current_draft(request, jurisdiction=jurisdiction or None, resume_latest=False)
    if draft is not None:
        update_draft_from_case_data(draft, case_data)
    return draft


def sync_current_draft_upload_data(request, upload_data: Mapping[str, Any]) -> FilingDraft | None:
    """Compatibility hook for a session endpoint that just saved upload data."""

    jurisdiction = _as_string(request.session.get("jurisdiction"))
    draft = get_current_draft(request, jurisdiction=jurisdiction or None, resume_latest=False)
    if draft is not None:
        sync_documents_from_upload_data(draft, upload_data)
    return draft


def _sync_parties_from_case_data(draft: FilingDraft, case_data: Mapping[str, Any]) -> None:
    petitioner = {
        "party_type": _as_string(
            _first_value(case_data, "petitioner_party_type", "party_type", "determined_party_type")
        ),
        "first_name": _as_string(_first_value(case_data, "petitioner_first_name", "first_name")),
        "middle_name": _as_string(_first_value(case_data, "petitioner_middle_name", "middle_name")),
        "last_name": _as_string(_first_value(case_data, "petitioner_last_name", "last_name")),
        "suffix": _as_string(_first_value(case_data, "petitioner_suffix", "suffix")),
        "email": _as_string(_first_value(case_data, "petitioner_email", "email")),
        "phone": _as_string(_first_value(case_data, "petitioner_phone", "phone")),
        "address_line_1": _as_string(_first_value(case_data, "petitioner_address", "address", "address_line_1")),
        "address_line_2": _as_string(_first_value(case_data, "petitioner_address_line_2", "address_line2")),
        "city": _as_string(_first_value(case_data, "petitioner_city", "city")),
        "state": _as_string(_first_value(case_data, "petitioner_state", "state")),
        "zip_code": _as_string(_first_value(case_data, "petitioner_zip", "zip", "zip_code")),
        "metadata": {key: value for key, value in case_data.items() if key.startswith("petitioner_")},
    }
    _upsert_or_delete_party(draft, "petitioner", petitioner)

    name_sought = {
        "party_type": _as_string(_first_value(case_data, "new_name_party_type")),
        "first_name": _as_string(_first_value(case_data, "new_first_name")),
        "middle_name": _as_string(_first_value(case_data, "new_middle_name")),
        "last_name": _as_string(_first_value(case_data, "new_last_name")),
        "suffix": _as_string(_first_value(case_data, "new_suffix")),
        "metadata": {
            key: value for key, value in case_data.items() if key.startswith("new_") or key.startswith("reason_")
        },
    }
    _upsert_or_delete_party(draft, "name_sought", name_sought)


def _upsert_or_delete_party(draft: FilingDraft, role: str, values: dict[str, Any]) -> None:
    meaningful_fields = set(values) - {"metadata"}
    if any(values[field] for field in meaningful_fields):
        FilingParty.objects.update_or_create(draft=draft, role=role, sort_order=0, defaults=values)
    else:
        FilingParty.objects.filter(draft=draft, role=role, sort_order=0).delete()


def _upsert_document(
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
        "name": _as_string(_first_value(document_data, "name", "filename", "original_filename")),
        "original_filename": _as_string(_first_value(document_data, "original_filename", "filename", "name")),
        "size": _positive_int(_first_value(document_data, "size", "file_size")),
        "content_type": _as_string(_first_value(document_data, "content_type", "mime_type", "type")),
        "s3_key": _as_string(_first_value(document_data, "s3_key", "key")),
        "public_url": _as_string(_first_value(document_data, "url", "s3_url", "file_url", "download_url")),
        "filing_type_code": _as_string(
            _first_value(config_data, "filing_type", "lead_filing_type", "filing_type_code")
        ),
        "filing_type_name": _as_string(_first_value(config_data, "filing_type_name", "lead_filing_type_name")),
        "document_type_code": _as_string(
            _first_value(config_data, "document_type", "lead_document_type", "document_type_code")
        ),
        "document_type_name": _as_string(_first_value(config_data, "document_type_name", "lead_document_type_name")),
        "filing_component_code": _as_string(
            _first_value(config_data, "filing_component", "lead_filing_component", "filing_component_code")
        ),
        "filing_component_name": _as_string(
            _first_value(config_data, "filing_component_name", "lead_filing_component_name")
        ),
        "courtesy_copy_email": _as_string(_first_value(config_data, "cc_email", "lead_cc_email")),
        "metadata": {"file": document_data, "config": config_data},
    }
    document, _created = FilingDocument.objects.update_or_create(
        draft=draft,
        role=role,
        sort_order=sort_order,
        defaults=defaults,
    )
    return document


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None
