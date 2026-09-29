"""Account-free guidance, never recorded or accepted as a live fee quote."""

import re
from decimal import Decimal, InvalidOperation

from efile.services.filing_plans import _codes
from efile.utils.config_loader import config_loader


def money(value):
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def contingent_fee(draft, document, rules):
    """First matching rule; thresholds are inclusive and ordered in YAML."""
    for rule in rules:
        if rule.get("initial_only") and (draft.existing_case != "new" or document.role != "lead"):
            continue
        if not re.search(rule["case_pattern"], draft.case_type_name, re.I):
            continue
        if not re.search(rule["filing_pattern"], document.filing_type_name, re.I):
            continue
        amount = money(draft.amount_in_controversy)
        bands = rule["bands"]
        if amount is not None:
            bands = next(([b] for b in bands if b.get("up_to") is None or amount <= Decimal(str(b["up_to"]))), [])
        if not bands:
            return None
        return min(Decimal(str(b["low"])) for b in bands), max(Decimal(str(b["high"])) for b in bands)
    return None


def estimate_fees(draft):
    config = (config_loader.load_jurisdiction_config(draft.jurisdiction) or {}).get("fee_estimates", {})
    options = _codes(
        draft.jurisdiction,
        f"{draft.court_code}/filing_types/",
        initial="false" if draft.existing_case == "existing" else "true",
        category_id=draft.case_category_code,
        type_id=draft.case_type_code,
    )
    by_code = {str(option.get("code")): option for option in options}
    rows = []
    low = high = Decimal("0")
    unknown = False
    for document in draft.documents.all():
        option = by_code.get(document.filing_type_code, {})
        fee = money(option.get("fee"))
        # Tyler lists amount-in-controversy fees as "0.00"; a matching rule beats a false $0.
        bounds = (fee, fee) if fee else contingent_fee(draft, document, config.get("rules", []))
        if bounds is None and fee is not None:
            bounds = (fee, fee)
        label = document.filing_type_name or document.name or "Document"
        if bounds is None:
            unknown = True
            rows.append({"label": label, "amount": "Not available yet"})
        else:
            minimum, maximum = bounds
            low += minimum
            high += maximum
            rows.append({"label": label, "amount": display_range(minimum, maximum)})
    return {
        "rows": rows,
        "total": display_range(low, high) if rows and not unknown else "",
        "partial": unknown,
        "note": config.get("note", ""),
    }


def display_range(low, high):
    return f"~${low:,.2f}" if low == high else f"${low:,.2f}–${high:,.2f}"
