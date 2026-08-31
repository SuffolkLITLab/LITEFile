"""Determine when the court needs an other party's mailing address."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from efile.utils.config_loader import config_loader


@dataclass(frozen=True)
class AddressRequirement:
    required: bool = False
    reason: str = ""


_DEFAULT_REASON = "The court requires a mailing address for this party before the filing can continue."


def _values(items) -> set[str]:
    return {str(item).strip().casefold() for item in items or [] if str(item).strip()}


def _matches(configured, *actual) -> bool:
    wanted = _values(configured)
    return bool(wanted.intersection(_values(actual)))


def _metadata_requires_address(party, party_types) -> bool:
    if party is None:
        return False
    for party_type in party_types or []:
        if str(party_type.get("code") or "") != str(party.party_type or ""):
            continue
        return party_type.get("address_required") is True
    return False


def party_address_requirement(draft, party=None, *, party_types=None) -> AddressRequirement:
    """Resolve live metadata and layered YAML rules for one other party.

    The default is deliberately optional. A state/case/court configuration can
    require every address, or only addresses selected by party type, filing
    type, or optional-service code. ``get_case_type_config`` has already merged
    the base, state, case-type, and court layers before this function reads it.
    """
    if draft is None:
        return AddressRequirement()

    # The filer's own contact address is collected on a separate screen and is
    # always part of the EFSP user record. This resolver changes only the rule
    # for other parties.
    if party is not None and getattr(party, "role", "") == "filer":
        return AddressRequirement(True, _DEFAULT_REASON)

    if _metadata_requires_address(party, party_types):
        return AddressRequirement(True, _DEFAULT_REASON)

    jurisdiction = getattr(draft, "jurisdiction", "")
    if not jurisdiction:
        return AddressRequirement()
    case_type = getattr(draft, "case_type_name", "") or getattr(draft, "case_type_code", "") or ""
    jurisdiction_config = config_loader.load_jurisdiction_config(jurisdiction) or {}
    config = (
        config_loader.get_case_type_config(
            jurisdiction,
            case_type,
            court=getattr(draft, "court_code", ""),
        )
        or {}
    )
    rule: dict[str, Any] = config_loader._deep_merge(
        (jurisdiction_config.get("defaults") or {}).get("party_address") or {},
        config.get("party_address") or {},
    )
    court_config = (jurisdiction_config.get("court_specific_requirements") or {}).get(
        getattr(draft, "court_code", ""),
        {},
    )
    rule = config_loader._deep_merge(rule, court_config.get("party_address") or {})
    reason = str(rule.get("reason") or _DEFAULT_REASON)

    if rule.get("required") is True:
        return AddressRequirement(True, reason)

    if party is not None and _matches(
        rule.get("required_for_party_types"),
        party.party_type,
        party.party_type_name,
    ):
        return AddressRequirement(True, reason)

    document_manager = getattr(draft, "documents", None)
    documents = list(document_manager.all()) if hasattr(document_manager, "all") else []
    if any(
        _matches(rule.get("required_for_filing_types"), document.filing_type_code, document.filing_type_name)
        for document in documents
    ):
        return AddressRequirement(True, reason)

    selected_services = {str(code) for document in documents for code in (document.requested_optional_services or [])}
    selected_services.update(str(code) for code in (getattr(draft, "optional_services", None) or []))
    if _matches(rule.get("required_for_services"), *selected_services):
        return AddressRequirement(True, reason)

    return AddressRequirement()


def address_values(party) -> tuple[str, str, str, str]:
    return (party.address_line_1, party.city, party.state, party.zip_code)


def address_is_blank(party) -> bool:
    return not any((*address_values(party), party.address_line_2))


def address_is_complete(party) -> bool:
    return all(address_values(party))
