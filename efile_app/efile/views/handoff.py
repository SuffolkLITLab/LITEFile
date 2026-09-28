"""Source-authenticated API and filer-owned continuation/correction screens."""

import json
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from efile.api.suffolk_api_views import get_tyler_token
from efile.models import FilingDraft, HandoffDocumentUpdate, InterviewHandoff
from efile.services.current_drafts import attach_current_draft
from efile.services.draft_urls import draft_url
from efile.services.filings import describe_filing_detail, fetch_filing_detail
from efile.services.handoff import (
    HandoffError,
    create_correction,
    documents_replaced,
    fingerprint,
    issues_for,
    populate,
    receipt_for,
    record,
    resolve_metadata,
    submitted_filing_ids,
    validate_payload,
)
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.workflow import WorkflowStepKey

CLAIM_SALT = "litefile.handoff.claim.v1"
REPLACE_SALT = "litefile.handoff.replace.v1"


def _source(request):
    source = request.headers.get("X-LITEFile-Source", "")
    config = settings.LITEFILE_HANDOFF_SOURCES.get(source, {})
    expected = config.get("token", "")
    supplied = request.headers.get("Authorization", "")
    if not expected or not secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
        raise HandoffError("Source authentication required.", status=401)
    return source, config


def _read(request, config, *, require_lead=True):
    try:
        raw = request.POST.get("payload", "") if request.content_type == "multipart/form-data" else request.body
        if len(raw) > 512 * 1024:
            raise HandoffError("Handoff metadata exceeds 512 KB.", status=413)
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HandoffError("Send a JSON payload, with multipart PDF files when present.") from exc
    return validate_payload(payload, config, request.FILES, require_lead=require_lead)


def _response(request, receipt, *, created=False):
    draft = receipt.draft
    token = signing.dumps({"receipt": receipt.pk}, salt=CLAIM_SALT)
    return JsonResponse(
        {
            "draft_id": str(draft.pk),
            "state": "needs_input",
            "issues": issues_for(draft),
            "continue_url": request.build_absolute_uri(reverse("handoff_claim", args=[token])),
        },
        status=201 if created else 200,
    )


def _upload(payload, files, handler, keys):
    uploads = {}
    for document in payload.get("documents", []):
        result = handler.upload_file(
            files[document["id"]], file_type=document["role"], metadata={"sha256": document["sha256"]}
        )
        if not result.get("success"):
            raise HandoffError("Document storage is unavailable. Retry the same handoff.", status=503)
        keys.append(result["key"])
        uploads[document["id"]] = result
    return uploads


@csrf_exempt
@require_http_methods(["POST"])
def external_handoff(request):
    handler = S3UploadHandler()
    keys = []
    try:
        source, config = _source(request)
        payload = _read(request, config)
        digest = fingerprint(payload)
        existing = InterviewHandoff.objects.filter(source=source, source_id=payload["source_id"]).first()
        if existing:
            if existing.fingerprint != digest:
                raise HandoffError(
                    "This source_id already has a different handoff. Use the document-correction flow.", status=409
                )
            return _response(request, existing)
        try:
            with transaction.atomic():
                draft = FilingDraft.objects.create(
                    jurisdiction=payload["jurisdiction"], current_step=WorkflowStepKey.CASE_CONFIRMATION
                )
                receipt = InterviewHandoff.objects.create(
                    draft=draft,
                    source=source,
                    source_id=payload["source_id"],
                    idempotency_key=payload["idempotency_key"],
                    fingerprint=digest,
                    payload=payload,
                )
                uploads = _upload(payload, request.FILES, handler, keys)
                populate(draft, payload, uploads)
        except IntegrityError:
            for key in keys:
                handler.delete_file(key)
            keys = []
            existing = InterviewHandoff.objects.filter(
                source=source, idempotency_key=payload["idempotency_key"], fingerprint=digest
            ).first()
            if not existing:
                raise HandoffError("Idempotency key or source_id is already in use.", status=409) from None
            return _response(request, existing)
        # Metadata outages must not undo a successful durable handoff. Resolution
        # also runs when the filer opens the draft, after choosing a court.
        return _response(request, receipt, created=True)
    except HandoffError as exc:
        for key in keys:
            handler.delete_file(key)
        return JsonResponse({"error": str(exc)}, status=exc.status)


def _private(response):
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "same-origin"
    return response


@require_http_methods(["GET", "POST"])
def handoff_claim(request, token):
    try:
        value = signing.loads(token, salt=CLAIM_SALT, max_age=settings.LITEFILE_HANDOFF_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return _private(render(request, "efile/handoff_claim.html", {"expired": True}, status=410))
    receipt = get_object_or_404(InterviewHandoff, pk=value["receipt"])
    draft = receipt.draft
    if not request.user.is_authenticated or not get_tyler_token(request, draft.jurisdiction):
        request.session["handoff_continue"] = request.path
        return _private(redirect("efile_login", jurisdiction=draft.jurisdiction))
    if draft.user_id and draft.user_id != request.user.pk:
        return _private(render(request, "efile/handoff_claim.html", {"unavailable": True}, status=403))
    if request.method == "POST":
        with transaction.atomic():
            draft = FilingDraft.objects.select_for_update().get(pk=draft.pk)
            if draft.user_id not in (None, request.user.pk):
                return _private(JsonResponse({"error": "This draft belongs to another account."}, status=403))
            if draft.user_id is None:
                draft.user = request.user
                draft.save(update_fields=["user", "updated_at"])
        resolve_metadata(draft)
        attach_current_draft(request, draft)
        return _private(redirect("handoff_review", draft_id=draft.pk))
    return _private(
        render(request, "efile/handoff_claim.html", {"source": receipt.source, "jurisdiction": draft.jurisdiction})
    )


def _owned(request, draft_id):
    if not request.user.is_authenticated:
        raise HandoffError("Sign in to open this draft.", status=401)
    return get_object_or_404(FilingDraft, pk=draft_id, user=request.user)


def _issue_links(draft):
    issues = issues_for(draft)
    for issue in issues:
        url = reverse(issue["view"], kwargs={"jurisdiction": draft.jurisdiction})
        issue["url"] = draft_url(url + "?return_to=handoff", draft.pk)
    return issues


@require_http_methods(["GET", "POST"])
def handoff_review(request, draft_id):
    try:
        draft = _owned(request, draft_id)
    except HandoffError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    if draft.status != FilingDraft.Status.DRAFT:
        return _private(render(request, "efile/handoff_review.html", {"draft": draft, "closed": True}))
    attach_current_draft(request, draft)
    if request.method == "POST":
        resolve_metadata(draft)
        if request.POST.get("action") == "confirm":
            # Record the explicit review of existing selections. An unresolved
            # correction is kept open until its field actually has a value.
            remaining = []
            for path in draft.correction_fields:
                parts = path.split(".")
                if len(parts) == 3:
                    row = getattr(draft, parts[0]).filter(pk=parts[1]).first()
                    value = getattr(row, parts[2], "")
                else:
                    value = getattr(draft, path, "") if path != "documents" else documents_replaced(draft)
                if not value:
                    remaining.append(path)
                else:
                    record(draft, path, "user_confirmation", {"code": value})
            draft.correction_fields = remaining
            draft.save(update_fields=["correction_fields", "updated_at"])
            record(draft, "review", "user_confirmation", {"user_id": request.user.pk})
        return redirect("handoff_review", draft_id=draft.pk)
    receipt = receipt_for(draft)
    return _private(
        render(
            request,
            "efile/handoff_review.html",
            {
                "draft": draft,
                "issues": _issue_links(draft),
                "receipt": receipt,
                "documents": draft.documents.all(),
                "parties": draft.parties.all(),
                "can_return": bool(receipt and receipt.payload.get("return_url")),
                "review_url": draft_url(reverse("case_review", kwargs={"jurisdiction": draft.jurisdiction}), draft.pk),
                "case_url": draft_url(
                    reverse("extraction_review", kwargs={"jurisdiction": draft.jurisdiction}) + "?return_to=handoff",
                    draft.pk,
                ),
                "documents_url": draft_url(
                    reverse("organize_documents", kwargs={"jurisdiction": draft.jurisdiction}) + "?return_to=handoff",
                    draft.pk,
                ),
                "parties_url": draft_url(
                    reverse("parties", kwargs={"jurisdiction": draft.jurisdiction}) + "?return_to=handoff", draft.pk
                ),
            },
        )
    )


@require_http_methods(["GET", "POST"])
def correct_filing(request, draft_id):
    draft = None
    try:
        draft = _owned(request, draft_id)
        if not get_tyler_token(request, draft.jurisdiction):
            return redirect("efile_login", jurisdiction=draft.jurisdiction)
        filing_ids = submitted_filing_ids(draft.submission_response)
        if not filing_ids:
            raise HandoffError(
                "This submission has no confirmed filing identifier. Check its status before retrying.", status=409
            )
        details = []
        for filing_id in sorted(filing_ids):
            detail = describe_filing_detail(
                fetch_filing_detail(request, draft.jurisdiction, draft.court_code, filing_id)
            )
            if (
                not detail
                or detail.get("filing_id") != filing_id
                or detail.get("status", "").strip().lower() not in {"returned", "rejected"}
            ):
                raise HandoffError(
                    "The court has not confirmed a clerk return for every filing in this submission.", status=409
                )
            details.append(detail)
        detail = {
            **details[0],
            "comments": [comment for item in details for comment in item.get("comments", [])],
            "filings": details,
        }
        if request.method == "POST":
            revision = create_correction(draft, detail, request.POST.getlist("fields"))
            attach_current_draft(request, revision)
            return redirect("handoff_review", draft_id=revision.pk)
        choices = [
            (field, label)
            for field, label in (
                ("court_code", "Court"),
                ("case_category_code", "Case category"),
                ("case_type_code", "Case type"),
                ("documents", "PDF contents"),
            )
        ]
        choices.extend(
            (f"documents.{doc.pk}.{field}", f"{doc.name}: {label}")
            for doc in draft.documents.all()
            for field, label in (
                ("filing_type_code", "filing type"),
                ("document_type_code", "document type"),
                ("filing_component_code", "filing component"),
            )
        )
        choices.extend((f"parties.{party.pk}.party_type", f"{party}: party type") for party in draft.parties.all())
        return render(request, "efile/correct_filing.html", {"draft": draft, "detail": detail, "choices": choices})
    except HandoffError as exc:
        return render(request, "efile/correct_filing.html", {"draft": draft, "error": str(exc)}, status=exc.status)

    except (requests.RequestException, ValueError, TypeError):
        return render(
            request,
            "efile/correct_filing.html",
            {"draft": draft, "error": "The court status is unavailable. Try checking it again later."},
            status=503,
        )


@require_http_methods(["POST"])
def return_to_interview(request, draft_id):
    try:
        draft = _owned(request, draft_id)
        receipt = receipt_for(draft)
        if draft.status != FilingDraft.Status.DRAFT or not receipt or not receipt.payload.get("return_url"):
            raise HandoffError("This draft cannot return to its interview.", status=409)
        token = signing.dumps({"draft": draft.pk, "source": receipt.source}, salt=REPLACE_SALT)
        parts = urlsplit(str(receipt.payload["return_url"]))
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["litefile_correction"] = token
        return _private(
            redirect(str(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))))
        )
    except HandoffError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)


@csrf_exempt
@require_http_methods(["POST"])
def replace_documents(request):
    handler = S3UploadHandler()
    keys = []
    try:
        source, config = _source(request)
        # A correction may replace only the supporting PDF the clerk flagged.
        payload = _read(request, config, require_lead=False)
        token = request.headers.get("X-LITEFile-Correction", "")
        try:
            scope = signing.loads(token, salt=REPLACE_SALT, max_age=settings.LITEFILE_HANDOFF_TOKEN_MAX_AGE)
        except signing.BadSignature:
            raise HandoffError(
                "The document correction link expired. Return from LITEFile again.", status=403
            ) from None
        if scope.get("source") != source:
            raise HandoffError("The correction belongs to another source.", status=403)
        digest = fingerprint(payload)
        with transaction.atomic():
            draft = get_object_or_404(FilingDraft.objects.select_for_update(), pk=scope["draft"])
            receipt = receipt_for(draft)
            if (
                not receipt
                or receipt.source != source
                or receipt.source_id != payload["source_id"]
                or draft.jurisdiction != payload["jurisdiction"]
            ):
                raise HandoffError("The replacement does not belong to this interview.", status=403)
            prior = HandoffDocumentUpdate.objects.filter(
                source=source, idempotency_key=payload["idempotency_key"]
            ).first()
            if prior:
                if prior.draft_id != draft.pk or prior.fingerprint != digest:
                    raise HandoffError("The replacement idempotency key is already in use.", status=409)
            else:
                if draft.status != FilingDraft.Status.DRAFT:
                    raise HandoffError("Only an editable draft can receive replacement documents.", status=409)
                by_source_id = {}
                for event in draft.metadata_events.filter(kind="source_suggestion", path__startswith="documents."):
                    by_source_id[event.value["id"]] = event.path.split(".")[1]
                if not payload.get("documents") or any(doc["id"] not in by_source_id for doc in payload["documents"]):
                    raise HandoffError("Replace documents using their original source document ids.")
                updates = []
                for doc in payload["documents"]:
                    row = draft.documents.filter(pk=by_source_id[doc["id"]]).first()
                    if row is None:
                        raise HandoffError("A document was removed in LITEFile. Add its replacement there.", status=409)
                    updates.append((row, doc))
                HandoffDocumentUpdate.objects.create(
                    draft=draft, source=source, idempotency_key=payload["idempotency_key"], fingerprint=digest
                )
                uploads = _upload(payload, request.FILES, handler, keys)
                for row, doc in updates:
                    uploaded = uploads[doc["id"]]
                    row.s3_key = uploaded["key"]
                    row.public_url = uploaded["url"]
                    row.original_filename = uploaded["filename"]
                    row.size = uploaded["size"]
                    row.save(update_fields=["s3_key", "public_url", "original_filename", "size", "updated_at"])
                    record(
                        draft,
                        f"documents.{row.pk}",
                        "document_replacement",
                        {"sha256": doc["sha256"], "source": source},
                    )
                draft.correction_fields = [path for path in draft.correction_fields if path != "documents"]
                draft.quoted_fee_total = ""
                draft.quoted_fee_breakdown = []
                draft.selected_payment_account_id = ""
                draft.save(
                    update_fields=[
                        "correction_fields",
                        "quoted_fee_total",
                        "quoted_fee_breakdown",
                        "selected_payment_account_id",
                        "updated_at",
                    ]
                )
        return JsonResponse(
            {
                "draft_id": str(draft.pk),
                "state": "needs_input",
                "issues": issues_for(draft),
                "continue_url": request.build_absolute_uri(reverse("handoff_review", args=[draft.pk])),
            }
        )
    except HandoffError as exc:
        for key in keys:
            handler.delete_file(key)
        return JsonResponse({"error": str(exc)}, status=exc.status)
