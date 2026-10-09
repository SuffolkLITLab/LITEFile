"""Conservative Massachusetts docket inference from documented Trial Court formats.

Format references and official examples are recorded in tests/fixtures/massachusetts_dockets.json.
MACourts supplies the mapping from Trial Court identifiers to Tyler identifiers;
we never assume the two systems use the same number.
"""

import re

from efile.services.court_location import _finder, normalize_court_code

PROBATE_SITES = {
    "BA": "P72",
    "BR": "P73",
    "DU": "P74",
    "NA": "P75",
    "BE": "P76",
    "ES": "P77",
    "FR": "P78",
    "HD": "P79",
    "HS": "P80",
    "MI": "P81",
    "NO": "P82",
    "PL": "P83",
    "SU": "P84",
    "WO": "P85",
}


def infer_massachusetts_court(docket, courts, *, records=None):
    number = re.sub(r"[\s-]", "", str(docket or "")).upper()
    code, department = "", ""
    if match := re.fullmatch(r"[0-9]{2}([0-9]{2})[A-Z]{2}([0-9]{5,6})", number):
        code = str(int(match[1]))
        department = "Superior Court" if len(match[2]) == 5 else "District Court"
    elif match := re.fullmatch(r"([A-Z]{2})[0-9]{2}[ACDEWPRXS][0-9]{4}[A-Z]{2}", number):
        code = PROBATE_SITES.get(match[1], "")
        department = "Probate and Family Court"
    if not code:
        return None
    records = _finder().catalog.records if records is None else records
    candidates = {
        normalize_court_code(record.tyler_code)
        for record in records
        if record.court_code == code and record.department == department and record.tyler_code
    }
    if len(candidates) != 1:
        return None
    matches = [court for court in courts if normalize_court_code(court["value"]) in candidates]
    return matches[0] if len(matches) == 1 else None
