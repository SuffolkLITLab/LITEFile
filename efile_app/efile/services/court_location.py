"""Turn a place a filer knows into the courts that serve it.

Massachusetts is where this started. Its Trial Court departments do not
divide the state the same way -- the District Court that serves Somerville is
not in the county its Probate and Family Court is, and which Boston Municipal
Court division serves an address is a question about which side of a ward line
the building is on. A filer knows their town, or their address. They very often
do not know their county, and asking for it produces a confident wrong answer.

So Massachusetts asks for a place and hands it to `MACourts
<https://github.com/SuffolkLITLab/MACourts>`_, the shared library that owns the
Massachusetts court records and the jurisdiction rules. What comes back are
court *names*, which this module maps onto the e-filing service's own court
codes through the ``tyler_code`` each record carries, keeping only the courts
this environment actually offers.

Vermont is the simpler shape of the same problem. It has one Superior Court unit
per county, and the units are named after their counties -- but a filer knows
they live in Barre, not that Barre is in Washington County, and the Judiciary
calls it a unit rather than a county. `VTCourts
<https://github.com/SuffolkLITLab/VTCourts>`_ answers that from a town, a
county, or a ZIP, and identifies the court by unit name.

Location matching is always an alternative, never a requirement. Massachusetts
offers the department's court list beside the lookup; Vermont keeps its unit
dropdown, with the lookup as the way through for a filer who knows their town
and not their unit. A state that needs neither simply configures no matcher.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_STATE_SUFFIX = re.compile(r",?\s*\b(MA|Mass\.?|Massachusetts|VT|Vt\.?|Vermont)\b\.?\s*$", re.IGNORECASE)


class LocationLookupUnavailable(RuntimeError):
    """The matcher a jurisdiction asked for is not installed."""


def normalize_court_code(code: str) -> str:
    """Compare court codes the way two systems that both meant the same court do.

    Tyler writes a Juvenile Court session as ``0965:BE`` in one place and
    ``965:BE`` in another, and the case of the suffix is not consistent either.
    Neither difference means anything, so neither should decide a match.
    """

    parts = []
    for part in str(code or "").strip().split(":"):
        parts.append(part.lstrip("0") or "0" if part.isdigit() else part.casefold())
    return ":".join(parts)


def normalize_court_name(name: str) -> str:
    """Compare court names past the spacing and case nobody means anything by."""

    return " ".join(str(name or "").split()).casefold()


def parse_place(place: str) -> dict[str, str]:
    """Read a typed place into the fields a court lookup can use.

    Filers type what they have: "Cambridge", "Boston 02108", "24 Beacon St,
    Boston". Everything here is optional -- the matcher decides what it can do
    with a bare ZIP or a street with no city.
    """

    text = str(place or "").strip()
    postal_code = ""
    zip_match = _ZIP.search(text)
    if zip_match:
        postal_code = zip_match.group(1)
        text = (text[: zip_match.start()] + " " + text[zip_match.end() :]).strip()
    text = _STATE_SUFFIX.sub("", text).strip().strip(",").strip()

    street_address = ""
    city = text
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 2 and parts[0][:1].isdigit():
        street_address, city = parts[0], parts[1]
    elif len(parts) >= 2:
        city = parts[-1]
    elif parts and parts[0][:1].isdigit():
        # A street with no city. The ZIP, if one was typed, is what places it.
        street_address, city = parts[0], ""

    return {"street_address": street_address, "city": city, "postal_code": postal_code}


@lru_cache(maxsize=1)
def _finder():
    """The MACourts finder, built once: it loads court records and ward geometry."""

    from macourts import build_default_finder

    return build_default_finder()


def _massachusetts_matches(place: str, court_types: list[str]) -> list[dict[str, Any]]:
    try:
        from macourts import Location
    except ImportError as error:  # pragma: no cover - depends on the install
        raise LocationLookupUnavailable(
            "Massachusetts court lookup needs the MACourts package to be installed."
        ) from error

    fields = parse_place(place)
    if not any(fields.values()):
        return []
    location = Location(
        city=fields["city"] or None,
        postal_code=fields["postal_code"] or None,
        street_address=fields["street_address"] or None,
        state="Massachusetts",
    )
    matches = _finder().find(location, court_types=court_types or None)
    found = []
    for match in matches:
        for record in match.records:
            if not record.tyler_code:
                continue
            found.append(
                {
                    "code": str(record.tyler_code),
                    "name": match.name,
                    "department": match.department,
                    "reason": match.reasons[0].detail if match.reasons else "",
                }
            )
    return found


@lru_cache(maxsize=1)
def _vermont_finder():
    from vtcourts import build_default_finder

    return build_default_finder()


def _vermont_matches(place: str, court_types: list[str]) -> list[dict[str, Any]]:
    """Vermont units, found from a town, a county, or a ZIP.

    A unit is named after its county, so the court is identified by name rather
    than by code -- the e-filing service's own code for one of them carries a
    spelling the name does not.
    """

    try:
        from vtcourts import Location
    except ImportError as error:  # pragma: no cover - depends on the install
        raise LocationLookupUnavailable("Vermont court lookup needs the VTCourts package to be installed.") from error

    fields = parse_place(place)
    if not any(fields.values()):
        return []
    location = Location(
        city=fields["city"] or None,
        postal_code=fields["postal_code"] or None,
        street_address=fields["street_address"] or None,
        state="Vermont",
    )
    return [
        {
            "code": "",
            "court_name": f"{match.unit} Unit",
            "name": f"{match.unit} Unit",
            "department": match.county,
            "reason": match.reasons[0].detail if match.reasons else "",
        }
        for match in _vermont_finder().find_units(location)
    ]


MATCHERS = {"macourts": _massachusetts_matches, "vtcourts": _vermont_matches}


def find_courts(matcher: str, place: str, court_types: list[str], courts: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The courts in ``courts`` that serve ``place``, with the reason for each.

    ``courts`` is the pool the filer's earlier answers already narrowed to, so a
    match outside it -- a Housing Court returned while the filer is choosing a
    District Court, or a court this e-filing environment does not carry -- is
    dropped rather than offered.
    """

    lookup = MATCHERS.get(matcher)
    if lookup is None:
        raise LocationLookupUnavailable(f"No court location lookup is configured for '{matcher}'.")

    # A source identifies a court by whichever it actually holds: MACourts
    # records carry the e-filing service's own code, and Vermont's units are
    # known by name.
    by_code = {normalize_court_code(court["value"]): court for court in courts}
    by_name = {normalize_court_name(court["text"]): court for court in courts}
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in lookup(place, court_types):
        court = by_code.get(normalize_court_code(match["code"])) if match.get("code") else None
        if court is None and match.get("court_name"):
            court = by_name.get(normalize_court_name(match["court_name"]))
        if court is None or court["value"] in seen:
            continue
        seen.add(court["value"])
        results.append({**court, "reason": match["reason"], "matched_name": match["name"]})
    return results
