"""Version 1 interview handoff: facts in, durable editable filing out."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from efile.models import FilingDocument, FilingDraft, FilingMetadataEvent, FilingParty, InterviewHandoff
from efile.party_sides import side_for_party_type_name
from efile.services.document_checklists import normalize_name
from efile.services.filing_plans import _codes
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase, WorkflowStepKey

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
PERSON_FIELDS = (
    "first_name",
    "middle_name",
    "last_name",
    "suffix",
    "organization_name",
    "email",
    "phone",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "zip_code",
    "country",
)
CASE_FIELDS = ("court_name", "docket_number", "case_title")
HINT_FIELDS = (
    "filing_type_name_hints",
    "case_category_name_hints",
    "case_type_name_hints",
    "case_subtype_name_hints",
    "document_type_name_hints",
    "filing_component_name_hints",
)


class HandoffError(ValueError):
    def __init__(self, message, *, status=400):
        super().__init__(message)
        self.status = status


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _string(value, path, limit=255):
    if not isinstance(value, str) or len(value) > limit:
        raise HandoffError(f"{path} must be text of at most {limit} characters.")
    return value


def _object(value, path):
    if not isinstance(value, dict):
        raise HandoffError(f"{path} must be an object.")
    return value


def _hints(value, path):
    for field in HINT_FIELDS:
        if field in value:
            hints = value[field]
            if not isinstance(hints, list) or len(hints) > 20:
                raise HandoffError(f"{path}.{field} must be a list of up to 20 names.")
            for hint in hints:
                _string(hint, field)


def validate_payload(payload, source_config, files):
    _object(payload, "payload")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise HandoffError("Supported schema_version: 1.")
    for field in ("source_id", "idempotency_key", "jurisdiction"):
        if not _string(payload.get(field), field):
            raise HandoffError(f"{field} is required.")
    jurisdiction = payload["jurisdiction"]
    if (
        jurisdiction not in source_config.get("jurisdictions", [])
        or jurisdiction not in config_loader.get_available_jurisdictions()
    ):
        raise HandoffError("This source cannot send filings to that jurisdiction.", status=403)
    _hints(payload, "payload")
    _string(payload.get("filing_intent", ""), "filing_intent")
    case = _object(payload.get("case", {}), "case")
    if "existing_case" in case and type(case["existing_case"]) is not bool:
        raise HandoffError("case.existing_case must be true or false when known.")
    for field in CASE_FIELDS:
        _string(case.get(field, ""), f"case.{field}", FilingDraft._meta.get_field(field).max_length)
    _object(payload.get("known_filing_facts", {}), "known_filing_facts")
    parties = payload.get("parties", [])
    if not isinstance(parties, list) or len(parties) > 100:
        raise HandoffError("parties must be a list of up to 100 people or organizations.")
    for person in [_object(payload.get("filer", {}), "filer"), *parties]:
        _object(person, "person")
        for field in PERSON_FIELDS:
            _string(person.get(field, ""), field, FilingParty._meta.get_field(field).max_length)
        for field in ("is_self", "is_filing_party"):
            if field in person and type(person[field]) is not bool:
                raise HandoffError(f"{field} must be true or false.")
        for field in ("semantic_role", "case_side_hint"):
            _string(person.get(field, ""), field)
    return_url = payload.get("return_url", "")
    _string(return_url, "return_url", 2048)
    if return_url:
        try:
            parts = urlsplit(return_url)
        except ValueError as exc:
            raise HandoffError("return_url must be a valid URL.") from exc
        if (
            (
                parts.scheme != "https"
                and not (
                    settings.DEBUG
                    and parts.scheme == "http"
                    and source_config.get("allow_insecure_local_development") is True
                )
            )
            or parts.username
            or parts.password
            or f"{parts.scheme}://{parts.netloc}" not in source_config.get("return_origins", [])
        ):
            raise HandoffError("return_url must use an allowed HTTPS origin.")
    documents = payload.get("documents", [])
    if not isinstance(documents, list) or len(documents) > 20:
        raise HandoffError("documents must be a list of up to 20 PDFs.")
    ids = set()
    leads = 0
    for document in documents:
        _object(document, "document")
        key = _string(document.get("id"), "document.id", 100)
        if not key or key in ids:
            raise HandoffError("Each document needs a unique, nonempty id.")
        ids.add(key)
        if document.get("role") not in ("lead", "supporting"):
            raise HandoffError("Document role must be lead or supporting.")
        leads += document["role"] == "lead"
        _string(document.get("form_name", ""), "form_name")
        _hints(document, "document")
        uploaded = files.get(key)
        if uploaded is None:
            raise HandoffError(f"Upload the PDF for document {key}.")
        if uploaded.size > MAX_DOCUMENT_BYTES:
            raise HandoffError("Each PDF must be at most 10 MB.")
        digest = hashlib.sha256()
        prefix = uploaded.read(5)
        uploaded.seek(0)
        if prefix != b"%PDF-":
            raise HandoffError("Only PDF documents are accepted.")
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        if digest.hexdigest() != document.get("sha256"):
            raise HandoffError(f"Document hash mismatch: {key}.")
    if leads > 1 or (documents and leads != 1):
        raise HandoffError("A document bundle needs exactly one lead PDF.")
    if set(files) != ids or any(len(files.getlist(key)) != 1 for key in files):
        raise HandoffError("Upload each declared document exactly once.")
    return payload


def receipt_for(draft):
    while draft.correction_of_id:
        draft = draft.correction_of
    return InterviewHandoff.objects.filter(draft=draft).first()


def record(draft, path, kind, value):
    FilingMetadataEvent.objects.create(draft=draft, path=path, kind=kind, value=value)


def _person(draft, values, role, order):
    return FilingParty.objects.create(
        draft=draft,
        role=role,
        sort_order=order,
        **{key: values[key] for key in PERSON_FIELDS if key in values},
        is_self=values.get("is_self", False),
        is_filing_party=values.get("is_filing_party", False),
        party_role_hint=values.get("semantic_role", ""),
        party_side=side_for_party_type_name(values.get("case_side_hint", "")),
    )


def populate(draft, payload, uploads):
    case = payload.get("case", {})
    for field in CASE_FIELDS:
        setattr(draft, field, case.get(field, ""))
    if "existing_case" in case:
        draft.existing_case = ExistingCase.EXISTING if case["existing_case"] else ExistingCase.NEW
    # Keep arbitrary legal facts in the source receipt. Copy only supported
    # questionnaire answers into the ordinary filing UI.
    facts = payload.get("known_filing_facts", {})
    draft.supplemental_fields = {key: facts[key] for key in ("has_children", "child_count") if key in facts}
    draft.save()
    filer = payload.get("filer", {})
    if filer:
        _person(draft, filer, "filer", 0)
    for i, party in enumerate(payload.get("parties", [])):
        # Explicit self identity can merge the caption row with the filer.
        if party.get("is_self") and filer:
            row = draft.parties.get(role="filer")
            for field in PERSON_FIELDS:
                if not getattr(row, field) and party.get(field):
                    setattr(row, field, party[field])
            row.is_self = True
            row.is_filing_party = party.get("is_filing_party", True)
            row.party_role_hint = party.get("semantic_role", "")
            row.party_side = side_for_party_type_name(party.get("case_side_hint", ""))
            row.save()
        else:
            _person(draft, party, "other", i)
    for i, document in enumerate(payload.get("documents", [])):
        uploaded = uploads[document["id"]]
        row = FilingDocument.objects.create(
            draft=draft,
            role=document["role"],
            sort_order=i,
            name=document.get("form_name") or uploaded["filename"],
            original_filename=uploaded["filename"],
            size=uploaded["size"],
            content_type="application/pdf",
            s3_key=uploaded["key"],
            public_url=uploaded["url"],
        )
        record(draft, f"documents.{row.pk}", "source_suggestion", document)
    record(draft, "handoff", "source_suggestion", payload)


def unique_match(options, hints):
    wanted = {normalize_name(name) for name in hints if name}
    matches = {
        str(option["code"]): option
        for option in options
        if option.get("code") and normalize_name(option.get("name")) in wanted
    }
    return next(iter(matches.values())) if len(matches) == 1 else None


def court_hints(draft, payload):
    hints = [draft.court_name]
    # Vermont's court list calls each county a Unit; the legal interview calls
    # it a Family Division. This is a semantic alias, never a cached court code.
    county = payload.get("case", {}).get("county", "")
    if draft.jurisdiction == "vermont" and isinstance(county, str) and county:
        county = county.removesuffix(" County")
        hints.append(f"{county} Unit")
    return hints


def resolve_metadata(draft):
    """Resolve only empty fields and only unambiguous live semantic matches."""
    receipt = receipt_for(draft)
    if not receipt or draft.status != FilingDraft.Status.DRAFT:
        return
    payload = receipt.payload
    configuration = config_loader.load_jurisdiction_config(draft.jurisdiction) or {}
    intent = configuration.get("handoff", {}).get("filing_intents", {}).get(payload.get("filing_intent"), {})

    def choose(obj, field, options, hints):
        # Corrections stay blank until the filer chooses; don't restore the
        # very suggestion the clerk returned.
        path = (
            field
            if obj is draft
            else f"{'documents' if isinstance(obj, FilingDocument) else 'parties'}.{obj.pk}.{field}"
        )
        if getattr(obj, field) or path in draft.correction_fields:
            return
        option = unique_match(options, hints)
        if option:
            setattr(obj, field, str(option["code"]))
            name_field = field.replace("_code", "_name") if field != "party_type" else "party_type_name"
            setattr(obj, name_field, str(option.get("name", "")))
            obj._metadata_kind = "live_resolution"
            obj.save(update_fields=[field, name_field, "updated_at"])
            del obj._metadata_kind
            record(
                draft,
                path,
                "live_resolution",
                {"code": str(option["code"]), "name": option.get("name"), "source": "court metadata"},
            )

    choose(draft, "court_code", _codes(draft.jurisdiction, "", with_names=True), court_hints(draft, payload))
    if not draft.court_code:
        return
    timing = "Subsequent" if draft.existing_case == ExistingCase.EXISTING else "Initial"
    choose(
        draft,
        "case_category_code",
        _codes(draft.jurisdiction, f"{draft.court_code}/categories", timing=timing, fileable_only=True),
        intent.get("case_category_name_aliases", []) + payload.get("case_category_name_hints", []),
    )
    if not draft.case_category_code:
        return
    choose(
        draft,
        "case_type_code",
        _codes(
            draft.jurisdiction, f"{draft.court_code}/case_types/", category_id=draft.case_category_code, timing=timing
        ),
        intent.get("case_type_name_aliases", []) + payload.get("case_type_name_hints", []),
    )
    if not draft.case_type_code:
        return
    options = _codes(
        draft.jurisdiction,
        f"{draft.court_code}/filing_types/",
        initial="false" if draft.existing_case == ExistingCase.EXISTING else "true",
        category_id=draft.case_category_code,
        type_id=draft.case_type_code,
    )
    for document in draft.documents.all():
        suggestion = draft.metadata_events.filter(path=f"documents.{document.pk}", kind="source_suggestion").first()
        hints = suggestion.value if suggestion else {}
        curated = intent.get("documents", {}).get(hints.get("id", ""), {})
        choose(
            document,
            "filing_type_code",
            options,
            curated.get("filing_type_name_aliases", [])
            + (
                hints.get("filing_type_name_hints", [])
                or (
                    intent.get("filing_type_name_aliases", []) + payload.get("filing_type_name_hints", [])
                    if document.role == "lead"
                    else [hints.get("form_name", "")]
                )
            ),
        )
        if document.filing_type_code:
            for field, endpoint in (
                ("document_type_code", "document_types"),
                ("filing_component_code", "filing_components"),
            ):
                choices = _codes(
                    draft.jurisdiction, f"{draft.court_code}/filing_types/{document.filing_type_code}/{endpoint}"
                )
                choose(document, field, choices, hints.get(field.replace("_code", "_name_hints"), []))
    party_options = _codes(draft.jurisdiction, f"{draft.court_code}/case_types/{draft.case_type_code}/party_types")
    for party in draft.parties.all():
        if party.role == "filer" and not (party.is_self or party.is_filing_party):
            continue
        hints = [party.party_role_hint]
        exact = unique_match(party_options, hints)
        candidates = (
            [option for option in party_options if side_for_party_type_name(option.get("name", "")) == party.party_side]
            if party.party_side
            else []
        )
        if not exact and len(candidates) == 1:
            hints = [candidates[0]["name"]]
        choose(party, "party_type", party_options, hints)


def issues_for(draft):
    """Editable requirements, not a claim that the final EFSP payload is valid."""
    issues = []

    def need(path, value, message, view):
        if not value or path in draft.correction_fields:
            issues.append({"code": f"{path.split('.')[-1]}_required", "path": path, "message": message, "view": view})

    for field, label in (
        ("existing_case", "whether this starts a new case"),
        ("court_code", "the court"),
        ("case_category_code", "the case category"),
        ("case_type_code", "the case type"),
    ):
        need(field, getattr(draft, field), f"Choose {label}.", "extraction_review")
    if draft.existing_case == ExistingCase.EXISTING:
        need("previous_case_id", draft.previous_case_id, "Find and confirm the existing court case.", "case_lookup")
    need("main_document", draft.documents.filter(role="lead").exists(), "Add the main PDF.", "upload_documents")
    need(
        "document_checklist_acknowledged",
        draft.document_checklist_acknowledged,
        "Check that all required documents are included.",
        "document_checklist",
    )
    for doc in draft.documents.all():
        for field, label in (
            ("filing_type_code", "filing type"),
            ("document_type_code", "document type"),
            ("filing_component_code", "filing component"),
        ):
            need(
                f"documents.{doc.pk}.{field}",
                getattr(doc, field),
                f"Choose the {label} for {doc.name}.",
                "organize_documents",
            )
    filer = draft.parties.filter(role="filer").first()
    for field in ("first_name", "last_name", "address_line_1", "city", "state", "zip_code", "email"):
        need(f"filer.{field}", getattr(filer, field, ""), f"Add your {field.replace('_', ' ')}.", "your_information")
    need(
        "filing_party", draft.parties.filter(is_filing_party=True).exists(), "Choose who you are filing for.", "parties"
    )
    for party in draft.parties.all():
        if party.role != "filer" or party.is_self or party.is_filing_party:
            need(
                f"parties.{party.pk}.party_type",
                party.party_type,
                f"Choose the court's party type for {party}.",
                "parties",
            )
    from efile.services.party_requirements import address_is_blank, address_is_complete, party_address_requirement
    from efile.services.people import get_case_questions, needs_amount_in_controversy

    for party in draft.parties.exclude(role="filer"):
        need(
            f"parties.{party.pk}.name",
            party.organization_name or (party.first_name and party.last_name),
            f"Add the name for this party: {party}.",
            "parties",
        )
        address_ok = address_is_complete(party) or (
            address_is_blank(party) and not party_address_requirement(draft, party).required
        )
        need(f"parties.{party.pk}.address", address_ok, f"Complete the address for {party}.", "parties")
    for question in get_case_questions(draft):
        if question.get("required"):
            answered = draft.supplemental_fields.get(question["name"]) not in (None, "")
            need(f"known_filing_facts.{question['name']}", answered, question["label"], "case_questions")
    if needs_amount_in_controversy(draft):
        need("amount_in_controversy", draft.amount_in_controversy, "Enter the amount in controversy.", "case_questions")
    need(
        "selected_payment_account_id",
        draft.selected_payment_account_id,
        "Choose a payment method or fee waiver and check fees.",
        "payment",
    )
    if "documents" in draft.correction_fields and draft.documents.exists():
        need("documents", False, "Replace the PDF the clerk asked you to correct.", "upload_documents")
    return issues


def full_snapshot(draft):
    data = model_to_dict(draft, exclude=["submission_snapshot"])
    data["documents"] = [model_to_dict(doc) for doc in draft.documents.all()]
    data["parties"] = [model_to_dict(party) for party in draft.parties.all()]
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


@transaction.atomic
def create_correction(draft, detail, fields):
    original = FilingDraft.objects.select_for_update().get(pk=draft.pk)
    if original.status != FilingDraft.Status.SUBMITTED or detail.get("status", "").strip().lower() not in {
        "rejected",
        "returned",
    }:
        raise HandoffError("Only a confirmed clerk return can be corrected. Check the filing status first.", status=409)
    existing = FilingDraft.objects.filter(correction_of=original).first()
    if existing:
        return existing
    if not fields:
        raise HandoffError("Choose what the clerk asked you to correct.")
    allowed = {"court_code", "case_category_code", "case_type_code", "documents"}
    allowed.update(
        f"documents.{doc.pk}.{field}"
        for doc in original.documents.all()
        for field in ("filing_type_code", "document_type_code", "filing_component_code")
    )
    allowed.update(f"parties.{party.pk}.party_type" for party in original.parties.all())
    if not set(fields) <= allowed:
        raise HandoffError("Unknown correction field.")
    # Older submissions did not yet capture a snapshot. Freeze one before any
    # copying; never update the original answers or response.
    if not original.submission_snapshot:
        FilingDraft.objects.filter(pk=original.pk).update(submission_snapshot=full_snapshot(original))
    values = model_to_dict(
        original, exclude=["id", "correction_of", "submission_snapshot", "clerk_return", "correction_fields"]
    )
    values["user_id"] = values.pop("user")
    values["plan_id"] = values.pop("plan")
    values.update(
        status=FilingDraft.Status.DRAFT,
        current_step=WorkflowStepKey.REVIEW,
        submitted_at=None,
        submission_response={},
        quoted_fee_total="",
        quoted_fee_breakdown=[],
        selected_payment_account_id="",
        selected_payment_account_name="",
        selected_payment_account_type="",
    )
    revision = FilingDraft.objects.create(**values, correction_of=original, clerk_return=detail)
    mapping = {}
    for relation in ("documents", "parties"):
        for row in getattr(original, relation).all():
            old_id = row.pk
            row.pk = None
            row.draft = revision
            row.save()
            mapping[f"{relation}.{old_id}"] = f"{relation}.{row.pk}"
    for event in original.metadata_events.all():
        path = event.path
        for old, new in mapping.items():
            if path == old or path.startswith(old + "."):
                path = new + path[len(old) :]
                break
        record(revision, path, event.kind, event.value)
    revised_fields = []
    for path in fields:
        for old, new in mapping.items():
            if path.startswith(old + "."):
                path = new + path[len(old) :]
                break
        revised_fields.append(path)
        parts = path.split(".")
        if len(parts) == 3:
            obj = getattr(revision, parts[0]).get(pk=parts[1])
            setattr(obj, parts[2], "")
            name_field = parts[2].replace("_code", "_name") if parts[2] != "party_type" else "party_type_name"
            setattr(obj, name_field, "")
            if parts[0] == "documents" and parts[2] == "filing_type_code":
                obj.document_type_code = ""
                obj.document_type_name = ""
                obj.filing_component_code = ""
                obj.filing_component_name = ""
                obj.requested_optional_services = []
            obj.save()
        elif path != "documents":
            setattr(revision, path, "")
            setattr(revision, path.replace("_code", "_name"), "")
        record(revision, path, "clerk_correction", {"returned_at": timezone.now().isoformat(), "detail": detail})
    # Dependent court metadata must be chosen again after changing its scope.
    if any(field in fields for field in ("court_code", "case_category_code", "case_type_code")):
        if "court_code" in fields:
            revision.case_category_code = ""
        revision.case_type_code = ""
        revision.documents.update(
            filing_type_code="", document_type_code="", filing_component_code="", requested_optional_services=[]
        )
        revision.parties.update(party_type="")
        revision.optional_services = []
    revision.correction_fields = revised_fields
    revision.save()
    return revision


def submitted_filing_ids(response):
    """Read only filing identifiers, never mistake an envelope ID for one."""
    ids = set()
    if isinstance(response, dict):
        for key, value in response.items():
            if key in {"filing_id", "filingId", "filingID"} and isinstance(value, str | int) and value:
                ids.add(str(value))
            elif key in {"filingIds", "filingIDs", "filing_ids"} and isinstance(value, list):
                ids.update(str(item) for item in value if type(item) in (str, int) and item)
            elif isinstance(value, dict | list):
                ids.update(submitted_filing_ids(value))
        category = response.get("identificationCategory", {})
        if isinstance(category, dict) and category.get("value") == "FILINGID":
            value = response.get("identificationID", {})
            if isinstance(value, dict):
                value = value.get("value")
            if value:
                ids.add(str(value))
    elif isinstance(response, list):
        for value in response:
            ids.update(submitted_filing_ids(value))
    return ids


def local_submission(user, jurisdiction, court_code, filing_id):
    for draft in FilingDraft.objects.filter(
        user=user, jurisdiction=jurisdiction, court_code=court_code, status=FilingDraft.Status.SUBMITTED
    ):
        if str(filing_id) in submitted_filing_ids(draft.submission_response):
            return draft
    return None


def matter_keys(user, jurisdiction, remote_filings):
    """Keep correction attempts in one filer-visible matter before case indexing."""
    drafts = list(FilingDraft.objects.filter(user=user, jurisdiction=jurisdiction).select_related("correction_of"))
    by_id = {draft.pk: draft for draft in drafts}
    roots = {}
    for draft in drafts:
        root = draft
        while root.correction_of_id and root.correction_of_id in by_id:
            root = by_id[root.correction_of_id]
        for filing_id in submitted_filing_ids(draft.submission_response):
            roots[filing_id] = root.pk
    tracked = {}
    for filing in remote_filings:
        root = roots.get(str(filing.get("filing_id", "")))
        if root and filing.get("case_tracking_id"):
            tracked[root] = str(filing["case_tracking_id"])
    return {filing_id: tracked.get(root, f"matter:{root}") for filing_id, root in roots.items()}
