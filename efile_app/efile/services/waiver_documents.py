"""Find waiver documents by their court filing type, not their filename."""

import re

from efile.models import FilingMetadataEvent
from efile.services.filing_plans import _codes
from efile.utils.config_loader import config_loader

WAIVER_TYPE = re.compile(
    # Up to three words may sit between "waive" and "fees", as in Vermont's
    # "Application to Waive Filing and Service Fees".
    r"fee[\s-]*waiv|waiv\w*\s+(?:[\w-]+\s+){0,3}?fees?\b|indigen|(?:in\s+)?forma\s+pauperis",
    re.I,
)


def _name(value):
    return " ".join(str(value or "").split()).casefold()


def _configured_names(draft, key):
    config = config_loader.load_jurisdiction_config(draft.jurisdiction).get("fee_waiver", {})
    return [_name(name) for name in config.get(key, [])]


def has_waiver_document(draft):
    fallback_names = _configured_names(draft, "fallback_filing_type_names")
    explicit_uploads = (
        set(
            draft.metadata_events.filter(kind="document_purpose", value={"purpose": "fee_waiver"}).values_list(
                "path", flat=True
            )
        )
        if fallback_names
        else set()
    )
    return any(
        WAIVER_TYPE.search(name)
        or (
            (item_id == "fee_waiver" or (not item_id and f"documents.{pk}" in explicit_uploads))
            and _name(name) in fallback_names
        )
        for pk, name, item_id in draft.documents.values_list("pk", "filing_type_name", "checklist_item_id")
    )


def record_waiver_upload(document):
    """Retain the filer's explicit purpose independently of checklist assignments."""
    FilingMetadataEvent.objects.create(
        draft=document.draft,
        path=f"documents.{document.pk}",
        kind="document_purpose",
        value={"purpose": "fee_waiver"},
    )


def waiver_filing_types(draft):
    options = _codes(
        draft.jurisdiction,
        f"{draft.court_code}/filing_types/",
        initial="false" if draft.existing_case == "existing" else "true",
        category_id=draft.case_category_code,
        type_id=draft.case_type_code,
    )
    preferred = _configured_names(draft, "preferred_filing_type_names")
    fallbacks = _configured_names(draft, "fallback_filing_type_names")
    # The upload defaults to the first type: jurisdiction preference, other
    # explicit fee waivers, then exact generic fallback names in configured order.
    matches = [
        item
        for item in options
        if item.get("code")
        and (WAIVER_TYPE.search(item.get("name", "")) or _name(item.get("name")) in fallbacks)
        and str(item.get("iscourtuseonly", "")).casefold() != "true"
        and not re.search(r"\b(order|denial|denied|objection)\b", item.get("name", ""), re.I)
    ]

    def preference(item):
        name = _name(item.get("name"))
        if name in preferred:
            return (0, preferred.index(name))
        if name in fallbacks:
            return (2, fallbacks.index(name))
        # Preserve general-before-program-specific behavior for other states.
        return (1, not re.search(r"\bfees?\b", name))

    return sorted(matches, key=preference)


def waiver_document_choices(draft, code):
    root = f"{draft.court_code}/filing_types/{code}"
    types = _codes(draft.jurisdiction, root + "/document_types")
    types = [item for item in types if str(item.get("iscourtuseonly", "")).casefold() != "true"]
    components = _codes(draft.jurisdiction, root + "/filing_components")
    lead = next((item for item in components if item.get("name", "").casefold() == "lead document"), None)
    if not types or lead is None:
        raise ValueError("We could not load the court's document choices. Try again.")
    return types, lead
