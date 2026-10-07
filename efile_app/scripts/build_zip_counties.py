"""Build efile/data/zip_counties.json.gz from Census 2020 relationship files.

Code search narrows courts by the county a case ZIP is in. Most states name
courts after counties; some (Massachusetts district courts) name them after
towns, so the table also maps each state's towns to their counties.

    curl -O https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt
    curl -O https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_cousubs_national.zip
    unzip 2020_Gaz_cousubs_national.zip
    uv run python scripts/build_zip_counties.py tab20_zcta520_county20_natl.txt 2020_Gaz_cousubs_national.txt

ZCTAs approximate ZIP codes; PO-box-only ZIPs have no ZCTA and stay unmatched.
"""

import csv
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "efile" / "data" / "zip_counties.json.gz"
COUNTY_SUFFIX = re.compile(
    r"\s+(County|Parish|Borough|City and Borough|Census Area|Municipality|Planning Region|city)$"
)
TOWN_SUFFIX = re.compile(
    r"\s+(city|town|township|village|borough|plantation|CCD|gore|grant|location|purchase|"
    r"unorganized territory|UT|charter township|municipality|district|precinct)$",
    re.IGNORECASE,
)


def main(zcta_path, cousub_path):
    states = {}
    towns = defaultdict(lambda: defaultdict(set))
    with open(cousub_path, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            row = {key.strip(): value.strip() for key, value in row.items()}
            states[row["GEOID"][:2]] = row["USPS"]
            towns[row["USPS"]][TOWN_SUFFIX.sub("", row["NAME"]).casefold()].add(row["GEOID"][:5])
    county_names = {}
    zips = defaultdict(lambda: defaultdict(list))
    with open(zcta_path, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle, delimiter="|"):
            county = row["GEOID_COUNTY_20"]
            county_names[county] = COUNTY_SUFFIX.sub("", row["NAMELSAD_COUNTY_20"])
            # Territories without county subdivisions in the gazetteer are skipped.
            if row["GEOID_ZCTA5_20"] and county[:2] in states:
                # Largest land overlap first, so a split ZIP leads with its main county.
                zips[states[county[:2]]][row["GEOID_ZCTA5_20"]].append((-int(row["AREALAND_PART"]), county))
    table = {}
    for state in sorted(set(zips) | set(towns)):
        table[state] = {
            "zips": {code: [county_names[c] for _, c in sorted(parts)] for code, parts in sorted(zips[state].items())},
            "towns": {
                name: sorted(county_names[c] for c in counties if c in county_names)
                for name, counties in sorted(towns[state].items())
                if name and any(c in county_names for c in counties)
            },
        }
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as handle:
        json.dump(table, handle, separators=(",", ":"), sort_keys=True)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, {sum(len(s['zips']) for s in table.values()):,} ZIPs)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
