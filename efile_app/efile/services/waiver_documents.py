"""Find waiver documents by their court filing type, not their filename."""

import re

from efile.services.filing_plans import _codes

WAIVER_TYPE = re.compile(
    # Up to three words may sit between "waive" and "fees", as in Vermont's
    # "Application to Waive Filing and Service Fees".
    r"fee[\s-]*waiv|waiv\w*\s+(?:[\w-]+\s+){0,3}?fees?\b|indigen|(?:in\s+)?forma\s+pauperis",
    re.I,
)


def has_waiver_document(draft):
    return any(WAIVER_TYPE.search(name) for name in draft.documents.values_list("filing_type_name", flat=True))


def waiver_filing_types(draft):
    options = _codes(
        draft.jurisdiction,
        f"{draft.court_code}/filing_types/",
        initial="false" if draft.existing_case == "existing" else "true",
        category_id=draft.case_category_code,
        type_id=draft.case_type_code,
    )
    # The upload defaults to the first type. Put general fee waivers ahead of
    # program-specific ones, such as Vermont's "COPE - ... In Forma Pauperis".
    matches = [
        item
        for item in options
        if WAIVER_TYPE.search(item.get("name", ""))
        and item.get("iscourtuseonly") not in (True, "true")
        and not re.search(r"\b(order|denial|denied|objection)\b", item.get("name", ""), re.I)
    ]
    return sorted(matches, key=lambda item: not re.search(r"\bfees?\b", item.get("name", ""), re.I))


def waiver_document_choices(draft, code):
    root = f"{draft.court_code}/filing_types/{code}"
    types = _codes(draft.jurisdiction, root + "/document_types")
    types = [item for item in types if item.get("iscourtuseonly") not in (True, "true")]
    components = _codes(draft.jurisdiction, root + "/filing_components")
    lead = next((item for item in components if item.get("name", "").casefold() == "lead document"), None)
    if not types or lead is None:
        raise ValueError("We could not load the court's document choices. Try again.")
    return types, lead
