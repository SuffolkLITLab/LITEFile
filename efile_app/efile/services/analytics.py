"""Workflow-only outbox and marginal counters; no persistent user identifiers."""

import hashlib
import logging
import re
from datetime import UTC, timedelta

from django.conf import settings
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
    }
)
DIMENSIONS = frozenset(
    {"case_type", "filer_side", "filing_for", "zip_code", "preparation", "original_pdf_state", "usage_frequency"}
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


def snapshot(draft, *, document=None):
    """All labels come from bounded configuration/enums, never supplied free text."""
    config = config_loader.load_jurisdiction_config(draft.jurisdiction)
    matched = _find_match(config.get("case_types", {}), draft.case_type_name)
    filer = draft.parties.filter(role="filer").first()
    side = (filer.party_side or side_for_party_type_name(filer.party_type_name)) if filer else ""
    zip_code = filer.zip_code.strip() if filer else ""
    prior = draft.user.filing_drafts.filter(status="submitted").exclude(pk=draft.pk).count()
    data = {
        "case_type": matched[0] if matched else "other_or_unknown",
        "filer_side": side if side in PartySide else "unknown",
        "filing_for": ("self" if filer.party_type else "someone_else") if filer else "unknown",
        "zip_code": zip_code[:5] if re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", zip_code) else "unknown",
        "usage_frequency": "first" if prior == 0 else "2_to_5" if prior < 5 else "6_or_more",
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
def _queue_event(draft, metric, operation, document=None):
    locked = FilingDraft.objects.select_for_update().get(pk=draft.pk)
    if (
        locked.deletion_pending
        or UsageEvent.objects.filter(draft=locked, metric=metric, operation=str(operation)).exists()
    ):
        return
    dimensions = snapshot(locked, document=document)
    dimensions["filing_kind"] = {ExistingCase.NEW: "new", ExistingCase.EXISTING: "existing"}.get(
        locked.existing_case, "unknown"
    )
    UsageEvent.objects.create(
        draft=locked, metric=metric, operation=str(operation), dimensions=dimensions, occurred_at=timezone.now()
    )


def record_event(draft, metric, *, operation="once", document=None):
    """A collection failure must not stop a filing. Outbox retries are idempotent."""
    if metric not in METRICS:
        raise ValueError("Unknown usage metric")
    try:
        if eligible(draft):
            _queue_event(draft, metric, operation, document)
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
    }
    for dimension, value in values.items():
        if not isinstance(value, str) or len(value) > 80:
            raise ValueError("Disallowed usage value")
        if dimension == "zip_code":
            valid = value == "unknown" or re.fullmatch(r"[0-9]{5}", value)
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
            count=F("count") + 1, contributors=F("contributors") + int(new_contributor), updated_at=timezone.now()
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
                }
            )
            continue
        grouped = {}
        for row in rows:
            if row.dimension == dimension:
                key = (row.filing_kind, row.value)
                grouped[key] = grouped.get(key, 0) + row.count
        for (kind, value), count in sorted(grouped.items()):
            result.append(
                {
                    "period": period,
                    "jurisdiction": jurisdiction,
                    "metric": metric,
                    "filing_kind": kind,
                    "dimension": dimension,
                    "value": value,
                    "count": count,
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
