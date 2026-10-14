"""Build reviewable court overrides from downloaded ILAO, Tyler and AOIC inputs.

Run with ``uv run --with openpyxl --with beautifulsoup4 --with pyyaml``.
Only exact, unique Tyler codes whose county matches the official clerk directory
are published. The official clerk phone takes precedence over the ILAO general
court phone; discrepancies remain in the audit. Cook uses the county-wide clerk
help line, never a guessed association between a courthouse row and a division.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import openpyxl
import yaml
from bs4 import BeautifulSoup

CLERKS_URL = "https://www.illinoiscourts.gov/courts/circuit-court/circuit-court-clerks/"
COOK_URL = "https://www.cookcountyclerkofcourt.org/contact-us"
CALENDAR_URL = "https://www.cookcountycourtil.gov/about/legal-court-holidays"


def digits(value):
    number = re.sub(r"\D", "", str(value or ""))
    if len(number) >= 11 and number.startswith("1"):
        number = number[1:]
    return number[:10]


def county_key(value):
    return re.sub(r"\W", "", str(value or "").strip().lower().removesuffix(" county"))


def official_phones(official_html):
    # AOIC splits Rock Island across adjacent strong tags and has an empty
    # strong tag after Cumberland. Join adjacent headings before splitting.
    official_html = re.sub(
        r"</strong>\s*<strong[^>]*>", " ", official_html, flags=re.IGNORECASE
    )
    official = {}
    for section in re.split(r"<strong[^>]*>", official_html)[1:]:
        county_html, separator, details = section.partition("</strong>")
        if not separator:
            continue
        county = BeautifulSoup(county_html, "html.parser").get_text(" ", strip=True)
        phone = re.search(
            r"Phone:\s*([\d /()-]+)",
            BeautifulSoup(details, "html.parser").get_text(" ", strip=True),
        )
        if phone and len(digits(phone[1])) == 10:
            key = county_key(county)
            if key in official:
                raise ValueError(f"Duplicate official clerk entry: {county}")
            official[key] = digits(phone[1])
    return official


def build(workbook, courts, official_html):
    sheet = openpyxl.load_workbook(workbook, read_only=True).active
    entries = iter(sheet.values)
    headers = next(entries)
    records = [dict(zip(headers, row, strict=True)) for row in entries if any(row)]
    live = {row["code"]: row["name"] for row in courts}
    counts = Counter(row["tyler_court_code"] for row in records)
    official = official_phones(official_html)
    overrides, audit = {}, []
    for row in records:
        code = row["tyler_court_code"]
        county = row["address_county"] or ""
        official_phone = official.get(county_key(county), "")
        status = "verified"
        if not code:
            status = "unmapped; Cook uses county-wide clerk contact separately"
        elif counts[code] != 1:
            status = "ambiguous duplicate code"
        elif code not in live:
            status = "code absent from Tyler snapshot"
        elif county_key(live[code]) != county_key(county):
            status = "county differs from Tyler name; review required"
        elif not official_phone:
            status = "no official clerk phone; review required"
        elif digits(row["phone"]) != official_phone:
            status = "verified official clerk phone; differs from ILAO court phone"
        if status.startswith("verified"):
            overrides[code] = {
                "contact": {
                    "name": f"{county} County Circuit Clerk",
                    "phone": f"{official_phone[:3]}-{official_phone[3:6]}-{official_phone[6:]}",
                    "url": CLERKS_URL,
                }
            }
        audit.append(
            [
                row["court_code"],
                row["name"],
                code or "",
                live.get(code, ""),
                row["phone"],
                official_phone,
                status,
            ]
        )
    for code, name in sorted(live.items()):
        if code == "cook" or code.startswith("cook:"):
            if official.get("cook") != "3126035030":
                raise ValueError(
                    "Cook clerk number changed; review before regeneration"
                )
            overrides[code] = {
                "contact": {
                    "name": "Cook County Circuit Clerk customer service",
                    "phone": "312-603-5030",
                    "url": COOK_URL,
                }
            }
            # Daily courtroom sessions do not establish clerk e-filing review
            # availability. Keep advisory clerk holiday guidance for all codes.
            overrides[code]["filing_timing"] = {
                "business_calendar": {
                    "excluded_holidays": [],
                    "source_url": CALENDAR_URL,
                }
            }
            audit.append(
                [
                    "",
                    "Cook county-wide clerk (official source)",
                    code,
                    name,
                    "",
                    "3126035030",
                    "verified county-wide contact; no division inference",
                ]
            )
        elif code not in overrides:
            audit.append(
                ["", "", code, name, "", "", "no verified contact; statewide fallback"]
            )
    return {"court_specific_requirements": overrides}, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workbook", "courts", "official_html", "overrides", "audit"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    overrides, audit = build(
        args.workbook,
        json.loads(args.courts.read_text()),
        args.official_html.read_text(),
    )
    args.overrides.write_text(
        yaml.safe_dump(overrides, sort_keys=False, allow_unicode=True)
    )
    with args.audit.open("w", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                "ilao_record",
                "ilao_name",
                "tyler_code",
                "tyler_name",
                "ilao_phone",
                "official_phone",
                "review_status",
            ]
        )
        writer.writerows(audit)
    print(
        f"Generated {len(overrides['court_specific_requirements'])} verified court contacts"
    )


if __name__ == "__main__":
    main()
