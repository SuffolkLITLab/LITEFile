"""Which courts serve a case ZIP: a location aid, never a jurisdiction ruling.

A state whose court selector configures a location matcher (MACourts,
VTCourts; see ``court_location``) answers from that package's own rules, and
falls back to counties only for courts the package has no record of. Any
other state goes through counties: a ZIP maps to counties through
``data/zip_counties.json.gz`` (Census ZCTAs, built by
``scripts/build_zip_counties.py``), and a court to counties through its code or
name -- Illinois codes start with the county (``cook:cvd1``), others name a
county or a town. A court neither can place (an appeals court, a statewide
division) stays in every ZIP's results: narrowing must never hide a court that
might hear the case.
"""

from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

from django.core.cache import cache

from efile.db_expressions import CourtCode

DATA = Path(__file__).resolve().parents[1] / "data"
ZIP_PATTERN = re.compile(r"[0-9]{5}(?:-[0-9]{4})?")


def _words(text):
    return re.findall(r"[a-z0-9]+", text.casefold().replace("’", "").replace("'", ""))


@lru_cache(maxsize=1)
def zip_table():
    with gzip.open(DATA / "zip_counties.json.gz", "rt", encoding="utf-8") as handle:
        return json.load(handle)


def state_code(jurisdiction):
    from efile.services.account_profile import default_state_code

    return default_state_code(jurisdiction).upper()


def zip_counties(jurisdiction, postal_code):
    """Every county a valid ZIP touches, largest share first; [] when none is known."""
    if jurisdiction == "illinois":
        # The state's own table also knows PO-box ZIPs that have no Census ZCTA.
        from efile.utils.zip_to_county_il import COUNTY_TO_ZIPS_IL

        counties = [name for name, codes in COUNTY_TO_ZIPS_IL.items() if postal_code[:5] in codes]
        if counties:
            return counties
    return zip_table().get(state_code(jurisdiction), {}).get("zips", {}).get(postal_code[:5], [])


def location_matcher(jurisdiction):
    from efile.services.court_selection import selector_config

    steps = (selector_config(jurisdiction) or {}).get("steps", [])
    return next((step["matcher"] for step in steps if step.get("matcher")), "")


def locate(index, postal_code):
    """The counties and court codes for a case ZIP, or None without one.

    Raises ValueError for a ZIP that is malformed or places nowhere in this
    jurisdiction, so the filer is told rather than shown every court.
    """
    if not postal_code:
        return None
    if not ZIP_PATTERN.fullmatch(postal_code):
        raise ValueError("Enter a five-digit ZIP code, or clear the ZIP filter.")
    counties = zip_counties(index.jurisdiction, postal_code)
    matcher = location_matcher(index.jurisdiction)
    if matcher:
        from efile.services.court_location import courts_for_postal_code

        found = courts_for_postal_code(matcher, postal_code[:5], index_courts(index))
        codes = found and found["matched"] | set(courts_serving(index, counties, only=found["unknown"]))
    else:
        codes = courts_serving(index, counties) if counties else None
    if codes is None:
        raise ValueError("We couldn't place this ZIP code here. Check it, or clear it to see every court.")
    return {"counties": counties, "courts": sorted(codes)}


def _contains(haystack, needle):
    return bool(needle) and any(haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


@lru_cache(maxsize=4096)
def court_counties(jurisdiction, code, name):
    """The counties a court's code or name places it in; empty when it names none."""
    state = zip_table().get(state_code(jurisdiction), {})
    counties = {county for names in state.get("zips", {}).values() for county in names}
    code_keys = {"".join(_words(part)) for part in code.split(":")}
    name_words = _words(name)
    found = {
        county for county in counties if "".join(_words(county)) in code_keys or _contains(name_words, _words(county))
    }
    if found:
        return frozenset(found)
    # Courts named for a town: the last dash-separated part of the name.
    town = " ".join(_words(re.split(r"\s+-+\s+", name.strip())[-1]))
    return frozenset(state.get("towns", {}).get(town, []))


def index_courts(index):
    """Code -> name for every court in an index, saved at refresh or looked up once."""
    if index.vocabulary.get("courts"):
        return index.vocabulary["courts"]
    key = f"filing-index-courts-v1:{index.pk}:{index.refreshed_at.isoformat()}"
    courts = cache.get(key)
    if courts is None:
        codes = index.paths.annotate(code=CourtCode("court")).values_list("code", flat=True).order_by().distinct()
        courts = {}
        for code in codes:
            path = index.paths.alias(code=CourtCode("court")).filter(code=code).only("court").first()
            courts[code] = path.court.get("name", code)
        cache.set(key, courts, timeout=None)
    return courts


def courts_serving(index, counties, only=None):
    """Court codes in ``counties``, plus every court whose county is unknown."""
    return sorted(
        code
        for code, name in index_courts(index).items()
        if (only is None or code in only)
        and (not (placed := court_counties(index.jurisdiction, code, name)) or placed & set(counties))
    )
