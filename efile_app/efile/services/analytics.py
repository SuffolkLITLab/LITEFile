"""Workflow-only outbox and marginal counters; no persistent user identifiers."""

import hashlib
import logging
import re
from datetime import UTC, timedelta

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from efile.models import FilingDraft, UsageContributor, UsageCounter, UsageEvent, UsageMatter
from efile.party_sides import PartySide, side_for_party_type_name
from efile.services.document_checklists import _find_match
from efile.utils.config_loader import config_loader
from efile.workflow import ExistingCase

logger = logging.getLogger(__name__)
METRICS = frozenset(
    {
        "started",
        "review",
        "submission_attempt",
        "transmitted",
        "submission_error",
        "document_uploaded",
        "matter_first_used",
        "court_accepted",
        "court_returned",
        "rejection_reason",
        "draft_discarded",
        "draft_resumed",
        "documents_transmitted",
        "pages_transmitted",
        "guided_forms_transmitted",
    }
)
DIMENSIONS = frozenset(
    {
        "case_type",
        "filer_side",
        "filing_for",
        "zip_code",
        "preparation",
        "original_pdf_state",
        "usage_frequency",
        "filing_type",
        "court",
        "has_attorney",
        "fee_waiver",
        "interview_source",
        "workflow_step",
        "rejection_reason",
    }
)

REJECTION_REASONS = frozenset(
    {
        "filing_type",
        "fees_or_waiver",
        "signature_or_notarization",
        "document_format",
        "missing_document",
        "service",
        "party_information",
        "other_or_unknown",
    }
)


def eligible(draft):
    return bool(
        settings.LITEFILE_ANALYTICS_ENABLED
        and not settings.DEBUG
        and not getattr(settings, "EFSP_TEST_DOCUMENT_URL", "")
        and draft.user_id
        and not draft.user.is_staff
        and not draft.user.is_superuser
        and not draft.user.analytics_excluded
        and draft.jurisdiction in config_loader.get_available_jurisdictions()
    )


def attorney_dimension(draft, filer):
    """Return a bounded answer only where the workflow establishes one."""
    linked_party = draft.parties.filter(
        source__in=("court", "added"),
        is_self=True,
    ).first()
    representation = ((linked_party or filer).representation or {}).get("status") if linked_party or filer else ""
    if representation == "represented":
        return "yes"
    # For a new case, selecting the signed-in filer as a filing party means
    # they are appearing for themselves. Existing-case imports deliberately
    # use "unknown" when the court supplies no attorney association, so do
    # not turn that absence into a claim that the party has no attorney.
    if draft.existing_case == ExistingCase.NEW and filer is not None and filer.party_type and filer.is_filing_party:
        return "no"
    return "unknown"


def snapshot(draft, *, document=None):
    """All labels come from bounded configuration/enums, never supplied free text."""
    config = config_loader.load_jurisdiction_config(draft.jurisdiction)
    matched = _find_match(config.get("case_types", {}), draft.case_type_name)
    filer = draft.parties.filter(role="filer").first()
    side = (filer.party_side or side_for_party_type_name(filer.party_type_name)) if filer else ""
    zip_code = filer.zip_code.strip() if filer else ""
    prior = draft.user.filing_drafts.filter(status="submitted").exclude(pk=draft.pk).count()
    waiver_types = set((config.get("fee_estimates") or {}).get("surcharges", {}).get("waiver_account_types", []))
    try:
        source = draft.handoff.source
    except ObjectDoesNotExist:
        source = "direct"
    allowed_sources = set(getattr(settings, "LITEFILE_HANDOFF_SOURCES", {}))
    interview_source = source if source in allowed_sources else "direct" if source == "direct" else "other_interview"
    data = {
        "case_type": matched[0] if matched else "other_or_unknown",
        "filer_side": side if side in PartySide else "unknown",
        "filing_for": ("self" if filer.party_type else "someone_else") if filer else "unknown",
        "zip_code": zip_code[:5] if re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", zip_code) else "unknown",
        "usage_frequency": "first" if prior == 0 else "2_to_5" if prior < 5 else "6_or_more",
        "filing_type": draft.filing_type_code or "unknown",
        "court": draft.court_code or "unknown",
        "has_attorney": attorney_dimension(draft, filer),
        "fee_waiver": (
            "submitted"
            if draft.selected_payment_account_type in waiver_types
            else "not_submitted"
            if draft.selected_payment_account_type
            else "unknown"
        ),
        "interview_source": interview_source,
        "workflow_step": str(draft.current_step or "unknown"),
    }
    if document is not None:
        data = {
            "preparation": document.preparation
            if document.preparation in {"unchanged", "flattened", "converted", "converted_flattened"}
            else "unknown"
        }
        data["original_pdf_state"] = (
            "fillable"
            if document.upload_has_form_fields is True
            else "no_form_fields"
            if document.upload_has_form_fields is False
            else "not_pdf_or_unknown"
        )
    return data


@transaction.atomic
def _queue_event(draft, metric, operation, document=None, *, quantity=1, extra_dimensions=None):
    locked = FilingDraft.objects.select_for_update().get(pk=draft.pk)
    if (
        locked.deletion_pending
        or UsageEvent.objects.filter(draft=locked, metric=metric, operation=str(operation)).exists()
    ):
        return
    dimensions = snapshot(locked, document=document)
    dimensions.update(extra_dimensions or {})
    dimensions["filing_kind"] = {ExistingCase.NEW: "new", ExistingCase.EXISTING: "existing"}.get(
        locked.existing_case, "unknown"
    )
    UsageEvent.objects.create(
        draft=locked,
        metric=metric,
        operation=str(operation),
        dimensions=dimensions,
        quantity=quantity,
        occurred_at=timezone.now(),
    )


def record_event(draft, metric, *, operation="once", document=None, quantity=1, extra_dimensions=None):
    """A collection failure must not stop a filing. Outbox retries are idempotent."""
    if metric not in METRICS:
        raise ValueError("Unknown usage metric")
    if type(quantity) is not int or quantity < 1 or quantity > 10_000:
        raise ValueError("Invalid usage quantity")
    try:
        if eligible(draft):
            _queue_event(
                draft,
                metric,
                operation,
                document,
                quantity=quantity,
                extra_dimensions=extra_dimensions,
            )
    except Exception:
        # Fixed message: exceptions can contain SQL parameters or case details.
        logger.error("Usage event could not be queued; collection is degraded")


@transaction.atomic
def count_event(event_id):
    event = (
        UsageEvent.objects.select_for_update(of=("self",))
        .select_related("draft__user")
        .filter(pk=event_id, counted_at__isnull=True)
        .first()
    )
    if event is None:
        return
    values = dict(event.dimensions)
    if set(values) - DIMENSIONS - {"filing_kind"} or event.metric not in METRICS:
        raise ValueError("Disallowed usage data")
    kind = values.pop("filing_kind")
    if kind not in {"new", "existing", "unknown"}:
        raise ValueError("Disallowed filing kind")
    allowed = {
        "case_type": set(config_loader.load_jurisdiction_config(event.draft.jurisdiction).get("case_types", {}))
        | {"other_or_unknown"},
        "filer_side": {str(side) for side in PartySide} | {"unknown"},
        "filing_for": {"self", "someone_else", "unknown"},
        "preparation": {"unchanged", "flattened", "converted", "converted_flattened", "unknown"},
        "original_pdf_state": {"fillable", "no_form_fields", "not_pdf_or_unknown"},
        "usage_frequency": {"first", "2_to_5", "6_or_more"},
        "has_attorney": {"yes", "no", "unknown"},
        "fee_waiver": {"submitted", "not_submitted", "unknown"},
        "interview_source": set(getattr(settings, "LITEFILE_HANDOFF_SOURCES", {})) | {"direct", "other_interview"},
        "workflow_step": {choice[0] for choice in FilingDraft._meta.get_field("current_step").choices} | {"unknown"},
        "rejection_reason": REJECTION_REASONS,
    }
    for dimension, value in values.items():
        if not isinstance(value, str) or len(value) > 80:
            raise ValueError("Disallowed usage value")
        if dimension == "zip_code":
            valid = value == "unknown" or re.fullmatch(r"[0-9]{5}", value)
        elif dimension in {"filing_type", "court"}:
            valid = value == "unknown" or bool(re.fullmatch(r"[A-Za-z0-9_.:/ -]{1,100}", value))
        else:
            valid = value in allowed[dimension]
        if not valid:
            raise ValueError("Disallowed usage value")
    day = event.occurred_at.astimezone(UTC).date()
    cells = [(day, "day", "all", "all"), (day.replace(day=1), "month", "all", "all")]
    cells.extend((day.replace(day=1), "month", dimension, value) for dimension, value in sorted(values.items()))
    for period, granularity, dimension, value in cells:
        counter, _ = UsageCounter.objects.get_or_create(
            day=period,
            granularity=granularity,
            jurisdiction=event.draft.jurisdiction,
            metric=event.metric,
            filing_kind=kind,
            dimension=dimension,
            value=value,
        )
        _, new_contributor = UsageContributor.objects.get_or_create(counter=counter, user_id=event.draft.user_id)
        UsageCounter.objects.filter(pk=counter.pk).update(
            count=F("count") + event.quantity,
            contributors=F("contributors") + int(new_contributor),
            updated_at=timezone.now(),
        )
    event.counted_at = timezone.now()
    # Keep only the operational deduplication marker after successful rollup.
    event.dimensions = {}
    event.save(update_fields=["counted_at", "dimensions"])


def drain_events(draft_ids=None, *, limit=1000):
    events = UsageEvent.objects.filter(counted_at__isnull=True).order_by("pk")
    if draft_ids is not None:
        events = events.filter(draft_id__in=draft_ids)
    for event_id in events.values_list("pk", flat=True)[:limit]:
        count_event(event_id)


def record_matter(draft):
    try:
        if not eligible(draft):
            return
        with transaction.atomic():
            # Operational aliases connect a plan's new-case filing to later
            # filings in its court case, including filings from another plan.
            aliases = []
            if draft.plan_id:
                aliases.append(f"plan:{draft.plan_id}")
            case_id = draft.previous_case_id or (draft.plan.case_tracking_id if draft.plan_id else "")
            if case_id:
                aliases.append(f"case:{draft.court_code}:{case_id}")
            if not aliases:
                aliases = [f"draft:{draft.pk}"]
            created = []
            for identity in sorted(hashlib.sha256(alias.encode()).hexdigest() for alias in aliases):
                _, new = UsageMatter.objects.get_or_create(
                    user=draft.user, jurisdiction=draft.jurisdiction, identity=identity
                )
                created.append(new)
            if all(created):
                _queue_event(draft, "matter_first_used", "once")
    except Exception:
        logger.error("Matter usage could not be queued; collection is degraded")


def record_transmission_details(draft):
    """Record countable submission contents without risking the filing path."""
    try:
        if not eligible(draft):
            return
        documents = list(draft.documents.select_related("extraction"))
        if documents:
            record_event(draft, "documents_transmitted", quantity=len(documents))
        page_counts = [
            document.extraction.total_pages
            for document in documents
            if hasattr(document, "extraction") and document.extraction.total_pages
        ]
        if len(page_counts) == len(documents) and page_counts:
            record_event(draft, "pages_transmitted", quantity=sum(page_counts))
        try:
            source_documents = draft.handoff.payload.get("documents", [])
        except ObjectDoesNotExist:
            source_documents = []
        guided_forms = sum(bool(document.get("form_name")) for document in source_documents)
        if guided_forms:
            record_event(draft, "guided_forms_transmitted", quantity=guided_forms)
    except Exception:
        logger.error("Transmission usage details could not be queued; collection is degraded")


def categorize_rejection(detail):
    """Map clerk comments to a fixed reporting category without retaining text."""
    text = " ".join(str(comment.get("text") or "") for comment in detail.get("comments") or []).casefold()
    rules = (
        ("fees_or_waiver", ("fee", "payment", "waiver", "indigen")),
        ("signature_or_notarization", ("signature", "signed", "notary", "notar")),
        ("filing_type", ("filing type", "document type", "event code")),
        ("missing_document", ("missing", "required document", "attach")),
        ("document_format", ("format", "pdf", "scan", "legible", "page", "margin")),
        ("service", ("service", "summons", "serve")),
        ("party_information", ("party", "plaintiff", "petitioner", "defendant", "respondent", "address")),
    )
    return next((category for category, terms in rules if any(term in text for term in terms)), "other_or_unknown")


def record_court_statuses(user, jurisdiction, filings):
    """Record terminal statuses only for filings LITEFile submitted for this account."""
    from efile.models import FilingIdentifier

    try:
        by_id = {
            str(row.get("filing_id") or ""): str(row.get("filing_status") or "").strip().lower()
            for row in filings
            if row.get("filing_id")
        }
        if not by_id:
            return
        identifiers = FilingIdentifier.objects.select_related("draft").filter(
            filing_id__in=by_id, draft__user=user, draft__jurisdiction=jurisdiction
        )
        for identifier in identifiers:
            status = by_id[identifier.filing_id]
            metric = (
                "court_accepted"
                if status == "accepted"
                else "court_returned"
                if status in {"rejected", "returned"}
                else None
            )
            if metric:
                record_event(identifier.draft, metric, operation=identifier.filing_id)
    except Exception:
        logger.error("Court outcome usage could not be queued; collection is degraded")


def record_court_detail(draft, filing_id, detail):
    try:
        status = str((detail or {}).get("status") or "").strip().lower()
        if status == "accepted":
            record_event(draft, "court_accepted", operation=filing_id)
        elif status in {"rejected", "returned"}:
            record_event(draft, "court_returned", operation=filing_id)
            record_event(
                draft,
                "rejection_reason",
                operation=filing_id,
                extra_dimensions={"rejection_reason": categorize_rejection(detail)},
            )
    except Exception:
        logger.error("Court detail usage could not be queued; collection is degraded")


def report_rows(jurisdictions, start, end, *, grouping="month", dimension="all"):
    if dimension not in DIMENSIONS | {"all"} or grouping not in {"day", "month"}:
        raise ValueError("Invalid report breakdown")
    # ZIP and other detailed breakdowns use full UTC months only.
    if dimension != "all" and (grouping != "month" or start.day != 1 or (end + timedelta(days=1)).day != 1):
        raise ValueError("Detailed reports require complete calendar months.")
    if grouping == "month" and (start.day != 1 or (end + timedelta(days=1)).day != 1):
        raise ValueError("Monthly reports require complete calendar months.")
    counters = UsageCounter.objects.filter(
        jurisdiction__in=jurisdictions, day__gte=start, day__lte=end, granularity=grouping
    )
    buckets = {}
    for row in counters.order_by("day", "jurisdiction", "metric", "filing_kind", "dimension", "value"):
        period = row.day.replace(day=1) if grouping == "month" else row.day
        key = (period, row.jurisdiction, row.metric)
        buckets.setdefault(key, []).append(row)
    result = []
    threshold = max(5, settings.LITEFILE_ANALYTICS_MIN_CONTRIBUTORS)
    for (period, jurisdiction, metric), rows in sorted(buckets.items()):
        # Suppress the entire requested breakdown, including all new/existing
        # subtotals and labels. No partial detailed breakdown can be subtracted
        # from a core total to reveal a hidden value.
        rows = [row for row in rows if row.dimension == dimension]
        if not rows:
            continue
        suppressed = any(row.contributors < threshold for row in rows)
        if suppressed:
            result.append(
                {
                    "period": period,
                    "jurisdiction": jurisdiction,
                    "metric": metric,
                    "filing_kind": "suppressed",
                    "dimension": dimension,
                    "value": "suppressed",
                    "count": "suppressed",
                    "contributors": "suppressed",
                }
            )
            continue
        grouped = {}
        for row in rows:
            if row.dimension == dimension:
                key = (row.filing_kind, row.value)
                grouped[key] = (row.count, row.contributors)
        for (kind, value), (count, contributors) in sorted(grouped.items()):
            result.append(
                {
                    "period": period,
                    "jurisdiction": jurisdiction,
                    "metric": metric,
                    "filing_kind": kind,
                    "dimension": dimension,
                    "value": value,
                    "count": count,
                    "contributors": contributors,
                }
            )
    return result


def collection_health(jurisdictions):
    counters = UsageCounter.objects.filter(jurisdiction__in=jurisdictions)
    return {
        "first_counter": counters.filter(granularity="day").order_by("day").values_list("day", flat=True).first(),
        "freshness": counters.aggregate(latest=Max("updated_at"))["latest"],
        "pending": UsageEvent.objects.filter(counted_at__isnull=True, draft__jurisdiction__in=jurisdictions).count(),
    }
