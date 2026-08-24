#!/usr/bin/env python3
"""Fill the corpus scenarios into court-published PDF templates."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "paired_manifest.jsonl"
TEMPLATES = ROOT / "official_templates"
INTERACTIVE = ROOT / "filled_pdfs" / "interactive"
FLATTENED = ROOT / "filled_pdfs" / "flattened"
MOTION_OUTPUTS = {
    "IL-09": "il_motion_01_continue.pdf",
    "IL-10": "il_motion_02_estate_extend_time.pdf",
    "MA-08": "ma_motion_01_district_continue.pdf",
    "MA-09": "ma_motion_02_family_late_certificate.pdf",
    "VT-08": "vt_motion_01_family_reconsider.pdf",
    "VT-09": "vt_motion_02_civil_extension.pdf",
}

VISIBLE_FIXTURE_REPLACEMENTS = {
    "ATJ-style synthetic estate motion": "ATJ 801.7 (08/25)",
    "Example Homes LLC": "Beacon Row Homes LLC",
    "Example Valley Middle School": "North Ridge Middle School",
    "Example": "Juniper",
    "Sample": "Linden",
    "Fiction": "Willow",
}

OFFICIAL_TEMPLATE_UNAVAILABLE_FIELDS = {
    "IL-01": {"document date"},
    "IL-02": {"document date"},
    "IL-04": {"document date"},
    "IL-07": {"document date"},
    "IL-08": {"document date"},
}


def clean(value: Any) -> Any:
    if isinstance(value, str):
        for old, new in VISIBLE_FIXTURE_REPLACEMENTS.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {
            key: clean(item)
            for key, item in value.items()
            if key not in {"email", "emails", "phone"}
        }
    return value


def reconcile_official_template(record: dict[str, Any]) -> dict[str, Any]:
    """Remove targets that the downloaded official form cannot display."""
    unavailable = OFFICIAL_TEMPLATE_UNAVAILABLE_FIELDS.get(record["id"], set())
    for container_name in ("expected_extraction", "directly_visible_or_labeled"):
        container = record.get(container_name, {})
        for field in unavailable:
            container.pop(field, None)
    if unavailable and "do_not_require" in record:
        record["do_not_require"] = sorted(set(record["do_not_require"]) | unavailable)
    if unavailable:
        explanation = (
            "The official template has no filer signature-date field, so document "
            "date is not required."
        )
        notes = record.get("notes", "").strip()
        if explanation not in notes:
            record["notes"] = f"{notes} {explanation}".strip()
    return record


def date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{month}/{day}/{year}"


def split_name(value: str) -> tuple[str, str, str]:
    parts = value.split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def split_address(value: str) -> tuple[str, str, str, str]:
    match = re.match(r"(.+?),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5})$", value)
    if not match:
        return value, "", "", ""
    return match.groups()


def line_wrap(value: str, width: int = 85) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if current and len(" ".join(current + [word])) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def common_rules(form_id: str, scenario: dict[str, Any]) -> dict[str, str]:
    # The Illinois maps below are grouped for readability. Supply neutral values
    # while the dict literal is evaluated; only the requested form's map is used.
    fallback: dict[str, Any] = {
        "county": "",
        "plaintiff": "",
        "defendant": "",
        "petitioner": "",
        "respondent": "",
        "current_name": "",
        "requested_name": "",
        "applicant": "",
        "moving_party": "",
        "case_title": " v. ",
        "case_caption": "",
        "case_number": "",
        "claim": "",
        "reason": "",
        "request": "",
        "motion_title": "",
        "relationship": "",
        "damages": "",
        "amount": "",
        "rent_due": "",
        "monthly_income": "0",
        "estate_value": "0",
        "plaintiff_address": "",
        "defendant_address": "",
        "petitioner_address": "",
        "residence": "",
        "property": "",
        "marriage_date": "2000-01-01",
        "separation_date": "2000-01-01",
        "dob": "2000-01-01",
        "residences": ["", ""],
        "children": [
            {"name": "", "dob": "2000-01-01"},
            {"name": "", "dob": "2000-01-01"},
        ],
        "parents": [{"name": "", "address": ""}, {"name": "", "address": ""}],
        "minor": {"name": "", "address": ""},
        "incidents": [
            {"date": "2000-01-01", "facts": ""},
            {"date": "2000-01-01", "facts": ""},
        ],
        "monthly_expenses": {
            "rent": "0",
            "utilities": "0",
            "food": "0",
            "transportation": "0",
            "childcare": "0",
        },
    }
    scenario = fallback | scenario
    scenario["minor"] = fallback["minor"] | scenario["minor"]
    if len(scenario["children"]) < 2:
        scenario["children"] = fallback["children"]
    signed = date(scenario["signed_date"])
    rules: dict[str, dict[str, str]] = {
        "IL-01": {
            "1 - County": scenario["county"],
            "2 - Plaintiff/Petitioner or In Re:": scenario["plaintiff"],
            "3 - Defendants/Respondents": scenario["defendant"],
            "7 - Defendant's Name": scenario["defendant"],
            "14 - Reason for Lawsuit": scenario["claim"],
            "26 - Amount of Money": scenario["damages"].replace("$", ""),
            "31 - Write what you want the judge to order the Defendant/Respondent to do": "Pay damages and court costs.",
            "Last - Signature2": f"/s/ {scenario['plaintiff']}",
            "Last - Print Name2": scenario["plaintiff"],
            "Last - Street Address2": scenario["plaintiff_address"],
        },
        "IL-02": {
            "A - County": scenario["county"],
            "1b - County": scenario["county"],
            "B - Petitioner": scenario["petitioner"],
            "C - Respondent": scenario["respondent"],
            "2d - Address": scenario["residences"][1],
            "3a - Married/United Date": date(scenario["marriage_date"]),
            "3c - Separated Date": date(scenario["separation_date"]),
            "5a - Child's Name": scenario["children"][0]["name"],
            "5a - Child's Age": "8",
            "5a - Child's Address": scenario["residences"][0],
            "5b - Child's Name": scenario["children"][1]["name"],
            "5b - Child's Age": "6",
            "5b - Child's Address": scenario["residences"][0],
            "A - Your Signature": f"/s/ {scenario['petitioner']}",
            "B - Print Your Name": scenario["petitioner"],
            "F - Address": scenario["residences"][0],
        },
        "IL-03": {
            "County": scenario["county"],
            "Plaintiff Name (First, Middle, Last) - 1": scenario["plaintiff"],
            "Defendants (First, middle, last name) - Line 1": scenario["defendant"],
            "1 - Property Address": scenario["property"],
            "2a - Amount": scenario["rent_due"].replace("$", ""),
            "3a - Amount": scenario["rent_due"].replace("$", ""),
            "3 - Date": signed,
            "Signature": f"/s/ {scenario['plaintiff']}",
            "Print Your Name": scenario["plaintiff"],
        },
        "IL-04": {
            "County": scenario["county"],
            "Plaintiff/Petitioner Name (First, Middle, Last)": scenario["plaintiff"],
            "Defendants (First, middle, last name or business name) - Line 1": scenario[
                "defendant"
            ],
            "1 - Name": scenario["plaintiff"],
            "2 - Defendant's Name and Address - Line 1": scenario["defendant"],
            "2 - Defendant's Name and Address - Line 2": scenario["defendant_address"],
            "3 - Amount": scenario["amount"].replace("$", ""),
            "5 - Line 1": scenario["reason"],
            "Signature": f"/s/ {scenario['plaintiff']}",
            "Print Your Name1": scenario["plaintiff"],
            "Street Address, Unit Number1": split_address(
                scenario["plaintiff_address"]
            )[0],
            "City State ZIP1": ", ".join(
                split_address(scenario["plaintiff_address"])[1:3]
            )
            + " "
            + split_address(scenario["plaintiff_address"])[3],
        },
        "IL-05": {
            "1 - County": scenario["county"],
            "2 - Name": scenario["current_name"],
            "4 - First Name": split_name(scenario["current_name"])[0],
            "5 - Middle Name": split_name(scenario["current_name"])[1],
            "6 - Last Name": split_name(scenario["current_name"])[2],
            "7 - First Name": split_name(scenario["requested_name"])[0],
            "8 - Middle Name": split_name(scenario["requested_name"])[1],
            "9 - Last Name": split_name(scenario["requested_name"])[2],
            "10 - Date": signed,
            "11 - Date of Birth": date(scenario["dob"]),
            "38 - First": split_name(scenario["current_name"])[0],
            "39 - Middle": split_name(scenario["current_name"])[1],
            "40 - Last": split_name(scenario["current_name"])[2],
            "41 - First": split_name(scenario["requested_name"])[0],
            "42 - Middle": split_name(scenario["requested_name"])[1],
            "43 - Last": split_name(scenario["requested_name"])[2],
            "45 - Date of Birth": date(scenario["dob"]),
            "69 - Signature": f"/s/ {scenario['current_name']}",
            "70 - Print Your Name": scenario["current_name"],
            "74 - Address": scenario["residence"],
        },
        "IL-06": {
            "1 - County": scenario["county"],
            "First Middle and Last Name of Minor Child": scenario["minor"]["name"],
            "First Middle Last Name": scenario["petitioner"],
            "Street Address Apt  City State Zip Code": scenario["petitioner_address"],
            "Relationship to Minor": scenario["relationship"],
            "First Middle Last Name_2": scenario["parents"][0]["name"],
            "Street Address Apt  City State Zip Code_2": scenario["parents"][0][
                "address"
            ],
            "Relationship to Minor_2": "parent",
            "First Middle Last Name_3": scenario["parents"][1]["name"],
            "Street Address Apt  City State Zip Code_3": scenario["parents"][1][
                "address"
            ],
            "Relationship to Minor_3": "parent",
            "Date - Page 1": signed,
            "Address - Page 1": scenario["minor"]["address"],
            "Value on Minor's Estate - Amount": scenario["estate_value"].replace(
                "$", ""
            ),
            "Print Name": scenario["petitioner"],
            "Signature": f"/s/ {scenario['petitioner']}",
            "Your Address": scenario["petitioner_address"],
        },
        "IL-07": {
            "2 - County": scenario["county"],
            "3 - Petitioner": scenario["petitioner"],
            "6 - Respondent": scenario["respondent"],
            "27 - Date": date(scenario["incidents"][0]["date"]),
            "101": scenario["incidents"][0]["facts"],
            "102": date(scenario["incidents"][1]["date"]),
            "104": scenario["incidents"][1]["facts"],
            "342": f"/s/ {scenario['petitioner']}",
            "343": scenario["petitioner"],
        },
        "IL-08": {
            "1 - County": scenario["county"],
            "2 - Plaintiff/Petitioner or In RE": scenario["case_title"].split(" v. ")[
                0
            ],
            "3 - Defendant/Respondent": scenario["case_title"].split(" v. ")[1],
            "4 - Case Number": scenario["case_number"],
            "6 - Your Name": scenario["applicant"],
            "8 - # of Adults": "1",
            "9 - Number of Children Under 18": "1",
            "19 - My Employment Total": scenario["monthly_income"]
            .split()[0]
            .replace("$", ""),
            "60 - Rent Total": scenario["monthly_expenses"]["rent"].replace("$", ""),
            "66 - Utilities Total": scenario["monthly_expenses"]["utilities"].replace(
                "$", ""
            ),
            "68 - Food Total": scenario["monthly_expenses"]["food"].replace("$", ""),
            "72 - Vehicle Total": scenario["monthly_expenses"][
                "transportation"
            ].replace("$", ""),
            "74 - Childcare Total": scenario["monthly_expenses"]["childcare"].replace(
                "$", ""
            ),
            "Last - Signature": f"/s/ {scenario['applicant']}",
            "Last - Print Name": scenario["applicant"],
        },
        "IL-09": {
            "County": scenario["county"],
            "Plaintiff/Petitioner or In Re:": scenario["plaintiff"],
            "Defendants/Respondents1:": scenario["defendant"],
            "Motion To": scenario["motion_title"],
            "Asking the Judge To1": f"{scenario['request']}. {scenario['reason']}",
            "Case Number": scenario["case_number"],
            "Last - Signature": f"/s/ {scenario['moving_party']}",
            "Last - Print Name": scenario["moving_party"],
            "3a - Date": signed,
        },
        "IL-10": {
            "County": scenario["county"],
            "Plaintiff/Petitioner or In Re:": scenario["case_caption"],
            "Motion To": scenario["motion_title"],
            "Asking the Judge To1": f"{scenario['request']}. {scenario['reason']}",
            "Case Number": scenario["case_number"],
            "Last - Signature": f"/s/ {scenario['moving_party']}",
            "Last - Print Name": scenario["moving_party"],
            "3a - Date": signed,
        },
    }
    if form_id in rules:
        return rules[form_id]

    if form_id == "MA-01":
        pa = split_address(scenario["plaintiff_address"])
        da = split_address(scenario["defendant_address"])
        return {
            "form1[0].#subform[0].DropDownList1[0]": "Middlesex",
            "form1[0].#subform[0].TextField1[0]": scenario["defendant"],
            "form1[0].#subform[0].TextField1[1]": scenario["plaintiff"],
            "form1[0].#subform[0].TextField2[9]": pa[0],
            "form1[0].#subform[0].TextField2[8]": pa[1],
            "form1[0].#subform[0].TextField2[7]": pa[2],
            "form1[0].#subform[0].TextField2[6]": pa[3],
            "form1[0].#subform[0].TextField2[0]": da[0],
            "form1[0].#subform[0].TextField2[5]": da[1],
            "form1[0].#subform[0].TextField2[3]": da[2],
            "form1[0].#subform[0].TextField2[2]": da[3],
            "form1[0].#subform[0].TextField4[1]": scenario["marriage_place"],
            "form1[0].#subform[0].TextField4[0]": date(scenario["marriage_date"]),
            "form1[0].#subform[0].TextField4[3]": scenario["last_lived_together"],
            "form1[0].#subform[0].TextField4[2]": date(scenario["separation_date"]),
            "form1[0].#subform[0].TextField5[0]": scenario["plaintiff"],
            "form1[0].#subform[0].DateTimeField1[0]": signed,
        }
    if form_id == "MA-02":
        address = split_address(scenario["addresses"][0])
        return {
            "form1[0].BodyPage1[0].Division[0]": "Norfolk",
            "form1[0].BodyPage1[0].TextField1[0]": scenario["petitioners"][0],
            "form1[0].BodyPage1[0].TextField1[1]": scenario["petitioners"][1],
            "form1[0].BodyPage1[0].TextField1[2]": address[0],
            "form1[0].BodyPage1[0].TextField1[3]": address[0],
            "form1[0].BodyPage1[0].TextField1[4]": address[1],
            "form1[0].BodyPage1[0].TextField1[5]": address[2],
            "form1[0].BodyPage1[0].TextField1[6]": address[3],
            "form1[0].BodyPage1[0].TextField1[7]": address[1],
            "form1[0].BodyPage1[0].TextField1[8]": address[2],
            "form1[0].BodyPage1[0].TextField1[9]": address[3],
            "form1[0].BodyPage1[0].TextField1[10]": scenario["marriage_place"],
            "form1[0].BodyPage1[0].TextField1[11]": date(scenario["marriage_date"]),
            "form1[0].BodyPage1[0].TextField1[14]": f"{scenario['children'][0]['name']}, {date(scenario['children'][0]['dob'])}",
            "form1[0].BodyPage1[0].DateTimeField1[0]": signed,
            "form1[0].BodyPage1[0].StaticText5[0]": f"/s/ {scenario['petitioners'][0]}",
            "form1[0].BodyPage1[0].TextField5[0]": scenario["petitioners"][0],
            "form1[0].BodyPage1[0].StaticText5[1]": f"/s/ {scenario['petitioners'][1]}",
            "form1[0].BodyPage1[0].TextField5[5]": scenario["petitioners"][1],
        }
    if form_id == "MA-03":
        pf, pm, pl = split_name(scenario["plaintiff"])
        df, dm, dl = split_name(scenario["defendant"])
        cf, cm, cl = split_name(scenario["child"]["name"])
        return {
            "form1[0].BodyPage1[0].Subform6[0].DropDownList1[0]": "Suffolk",
            "form1[0].BodyPage1[0].Subform6[0].TextField4[1]": pf,
            "form1[0].BodyPage1[0].Subform6[0].TextField4[2]": pl,
            "form1[0].BodyPage1[0].Subform6[0].TextField4[3]": pm,
            "form1[0].BodyPage1[0].Subform6[0].TextField4[4]": df,
            "form1[0].BodyPage1[0].Subform6[0].TextField4[5]": dl,
            "form1[0].BodyPage1[0].Subform6[0].TextField4[6]": dm,
            "form1[0].BodyPage1[0].S2[0].TextField4[2]": cf,
            "form1[0].BodyPage1[0].S2[0].TextField4[1]": cm,
            "form1[0].BodyPage1[0].S2[0].TextField4[0]": cl,
            "form1[0].BodyPage1[0].S2[0].TextField5[2]": date(scenario["child"]["dob"]),
            "form1[0].BodyPage1[0].S5[0].DateTimeField3[0]": "02/18/2021",
            "form1[0].BodyPage1[0].S8[0].TextField5[0]": scenario["plaintiff"],
            "form1[0].BodyPage1[0].S8[0].DateTimeField3[0]": signed,
        }
    if form_id == "MA-04":
        return {
            "form1[0].USPage1[0].DropDownList1[0]": "Essex",
            "form1[0].USPage1[0].TextField1[0]": scenario["defendant"],
            "form1[0].USPage1[0].TextField1[1]": scenario["plaintiff"],
            "form1[0].USPage1[0].TextField4[8]": "Salem, Massachusetts",
            "form1[0].USPage1[0].TextField4[9]": date(scenario["marriage_date"]),
            "form1[0].USPage1[0].TextField5[0]": scenario["plaintiff"],
            "form1[0].USPage1[0].DateTimeField1[0]": signed,
        }
    if form_id == "MA-05":
        cf, cm, cl = split_name(scenario["petitioner_current_name"])
        nf, nm, nl = split_name(scenario["requested_name"])
        return {
            "form1[0].BodyPage1[0].S1[0].DropDownList1[0]": "Worcester",
            "form1[0].BodyPage1[0].S1[0].fn[0]": cf,
            "form1[0].BodyPage1[0].S1[0].mn[0]": cm,
            "form1[0].BodyPage1[0].S1[0].ln[0]": cl,
            "form1[0].BodyPage1[0].S3[0].fn[0]": cf,
            "form1[0].BodyPage1[0].S3[0].mn[0]": cm,
            "form1[0].BodyPage1[0].S3[0].ln[0]": cl,
            "form1[0].BodyPage1[0].S3[0].add[0]": split_address(scenario["residence"])[
                0
            ],
            "form1[0].BodyPage1[0].S3[0].citytown[0]": "Worcester",
            "form1[0].BodyPage1[0].S3[0].state[0]": "MA",
            "form1[0].BodyPage1[0].S3[0].dob[0]": date(scenario["dob"]),
            "form1[0].BodyPage1[0].S5[0].from[0]": scenario["petitioner_current_name"],
            "form1[0].BodyPage1[0].S5[0].to[0]": scenario["requested_name"],
            "form1[0].BodyPage1[0].S5[0].reason[0]": scenario["reason"],
            "form1[0].BodyPage1[0].S7[0].nf[0]": nf,
            "form1[0].BodyPage1[0].S7[0].nm[0]": nm,
            "form1[0].BodyPage1[0].S7[0].nl[0]": nl,
            "form1[0].BodyPage1[0].S10[0].DateTimeField3[0]": signed,
            "form1[0].BodyPage1[0].S10[0].TextField5[0]": scenario[
                "petitioner_current_name"
            ],
        }
    if form_id == "MA-06":
        pa = split_address(scenario["plaintiff_address"])
        da = split_address(scenario["defendant_address"])
        return {
            "form1[0].#pageSet[0].Page1[0].name1[0]": scenario["plaintiff"],
            "form1[0].#pageSet[0].Page1[0].address1[0]": pa[0],
            "form1[0].#pageSet[0].Page1[0].city1[0]": f"{pa[1]}, {pa[2]} {pa[3]}",
            "form1[0].#pageSet[0].Page1[0].name2[0]": scenario["defendant"],
            "form1[0].#pageSet[0].Page1[0].address2[0]": da[0],
            "form1[0].#pageSet[0].Page1[0].city2[0]": f"{da[1]}, {da[2]} {da[3]}",
            "form1[0].#pageSet[0].Page1[0].ClaimDescription[0]": scenario[
                "claim_reason"
            ],
            "form1[0].#pageSet[0].Page1[0].NumericField1[0]": scenario[
                "claim_amount"
            ].replace("$", ""),
            "form1[0].#pageSet[0].Page1[0].NumericField2[0]": scenario[
                "court_costs"
            ].replace("$", ""),
            "form1[0].#pageSet[0].Page1[0].DateField1[0]": signed,
            "form1[0].#subform[0].signature_plaintiff[0]": f"/s/ {scenario['plaintiff']}",
        }
    if form_id == "MA-08":
        return {
            "form1[0].#subform[0].headingSub[0].TextField14[0]": scenario[
                "docket_number"
            ],
            "form1[0].#subform[0].TextField14[0]": scenario["plaintiff"],
            "form1[0].#subform[0].TextField14[1]": scenario["defendant"],
            "form1[0].#subform[0].DropDownList1[0]": scenario["division"],
            "form1[0].#subform[0].TextField8[0]": scenario["current_event"],
            "form1[0].#subform[0].TextField9[0]": date(scenario["current_date"]),
            "form1[0].#subform[0].TextField9[1]": date(scenario["requested_date"]),
            "form1[0].#subform[0].TextField14[2]": signed,
            "form1[0].#subform[0].TextField14[3]": scenario["moving_party"],
            "form1[0].#subform[0].TextField14[4]": f"/s/ {scenario['moving_party']}",
            "form1[0].#subform[2].TextField14[12]": scenario["docket_number"],
            "form1[0].#subform[2].TextField13[0]": scenario["reason"],
        }
    if form_id == "MA-09":
        return {
            "form1[0].BodyPage1[0].Divisions[0]": "Middlesex",
            "form1[0].BodyPage1[0].Docket[0]": scenario["docket_number"],
            "form1[0].BodyPage1[0].Motion1[0]": scenario["motion_title"],
            "form1[0].BodyPage1[0].Motion2[0]": scenario["motion_title"],
            "form1[0].BodyPage1[0].Plaintiff[0]": scenario["plaintiff"],
            "form1[0].BodyPage1[0].Defendant[0]": scenario["defendant"],
            "form1[0].BodyPage1[0].MovingParty[0]": scenario["moving_party"],
            "form1[0].BodyPage1[0].Sub1[0].Multi1[0]": f"{scenario['request']}. {scenario['reason']}",
            "form1[0].BodyPage1[0].DateTimeField1[0]": signed,
            "form1[0].BodyPage1[0].Print[0]": scenario["moving_party"],
        }
    if form_id == "MA-10":
        return {
            "form1[0].#subform[0].TextField1[0]": scenario["docket_number"],
            "form1[0].#subform[0].DropDownList1[0]": "Somerville",
            "form1[0].#subform[0].TextField2[0]": scenario["plaintiff"],
            "form1[0].#subform[0].TextField3[0]": scenario["plaintiff_address"],
            "form1[0].#subform[0].TextField5[0]": scenario["defendant"],
            "form1[0].#subform[0].TextField6[0]": scenario["defendant_address"],
            "form1[0].#subform[0].TextField1[5]": scenario["plaintiff"],
            "form1[0].#subform[0].TextField1[7]": scenario["defendant"],
            "form1[0].#subform[0].TextField1[11]": scenario["principal_due"].replace(
                "$", ""
            ),
            "form1[0].#subform[0].TextField1[6]": scenario["interest"].replace("$", ""),
            "form1[0].#subform[0].TextField1[9]": scenario["principal_due"].replace(
                "$", ""
            ),
            "form1[0].#subform[0].TextField1[12]": scenario["basis"],
            "form1[0].#subform[0].DateTimeField1[0]": signed,
            "form1[0].#subform[0].TextField1[1]": f"/s/ {scenario['plaintiff']}",
            "form1[0].#subform[0].TextField1[2]": scenario["plaintiff"],
            "form1[0].#subform[0].TextField1[4]": scenario["plaintiff_address"],
        }

    if form_id in {"VT-01", "VT-02"}:
        last = {"VT-01": ("52a", "53", "53a"), "VT-02": ("87", "87a", "88")}[form_id]
        return {
            "Unit": scenario["unit"],
            "Plaintiff Name": scenario["plaintiff"],
            "Defendant Name": scenario["defendant"],
            last[0]: signed,
            last[1]: f"/s/ {scenario['plaintiff']}",
            last[2]: scenario["plaintiff"],
        }
    if form_id == "VT-03":
        return {
            "Just County Names": scenario["unit"],
            "Plaintiff": scenario["plaintiff"],
            "Defendant": scenario["defendant"],
            "1": scenario["plaintiff"],
            "3": split_address(scenario["plaintiff_address"])[0],
            "5": ", ".join(split_address(scenario["plaintiff_address"])[1:3])
            + " "
            + split_address(scenario["plaintiff_address"])[3],
            "11": scenario["principal"].replace("$", ""),
            "12": scenario["interest"].replace("$", ""),
            "13": scenario["court_costs"].replace("$", ""),
            "15": scenario["defendant"],
            "17": split_address(scenario["defendant_address"])[0],
            "18": ", ".join(split_address(scenario["defendant_address"])[1:3])
            + " "
            + split_address(scenario["defendant_address"])[3],
            "19": scenario["claim"],
            "20": signed,
            "21": f"/s/ {scenario['plaintiff']}",
        }
    if form_id == "VT-04":
        return {
            "Just County Names": scenario["unit"],
            "Docket Number": scenario["case_number"],
            "Plaintiff": scenario["plaintiff"],
            "Defendant": scenario["defendant"],
            "1": scenario["defendant"],
            "2": scenario["defendant_response"],
            "6": scenario["affirmative_defenses"][0],
            "7": scenario["affirmative_defenses"][1],
            "13": signed,
            "13a": f"/s/ {scenario['defendant']}",
            "15": scenario["defendant"],
            "16": scenario["defendant_address"],
        }
    if form_id == "VT-05":
        return {
            "Unit": scenario["unit"],
            "1": scenario["plaintiff"],
            "3": scenario["defendant"],
            "28": date(scenario["most_recent_incident"]),
            "55": scenario["allegations"],
            "92": signed,
            "93": f"/s/ {scenario['plaintiff']}",
            "94": scenario["plaintiff"],
        }
    if form_id == "VT-06":
        cf, cm, cl = split_name(scenario["current_name"])
        nf, nm, nl = split_name(scenario["requested_name"])
        return {
            "County Name": scenario["unit"],
            "First": cf,
            "Middle": cm,
            "Last": cl,
            "1": scenario["birthplace"],
            "2": date(scenario["dob"]),
            "3": nf,
            "4": nm,
            "5": nl,
            "5a": "Middlebury",
            "15": signed,
            "15a": f"/s/ {scenario['current_name']}",
            "15b": scenario["current_name"],
            "16": scenario["residence"],
        }
    if form_id == "VT-07":
        minor = scenario["minor"]
        return {
            "Unit": scenario["unit"],
            "In re": minor["name"],
            "0": minor["name"],
            "6": scenario["reason"],
            "7": minor["name"],
            "8": date(minor["dob"]),
            "9": "12",
            "10": minor["grade"],
            "34": scenario["parents"][0]["name"],
            "39": scenario["parents"][0]["address"],
            "46": scenario["parents"][1]["name"],
            "51": scenario["parents"][1]["address"],
            "123": scenario["petitioner_proposed_guardian"],
            "125": split_address(scenario["guardian_address"])[0],
            "126": split_address(scenario["guardian_address"])[1],
            "127": split_address(scenario["guardian_address"])[2],
            "127a": split_address(scenario["guardian_address"])[3],
            "158": signed,
            "159": f"/s/ {scenario['petitioner_proposed_guardian']}",
            "160": scenario["petitioner_proposed_guardian"],
            "162": scenario["guardian_address"],
        }
    if form_id == "VT-08":
        return {
            "Unit": scenario["unit"],
            "Docket Number": scenario["case_number"],
            "Plaintiff": scenario["plaintiff"],
            "Defendant": scenario["defendant"],
            "1": scenario["moving_party"],
            "4": date(scenario["order_date"]),
            "10": scenario["reason"],
            "11": signed,
            "12": f"/s/ {scenario['moving_party']}",
        }
    if form_id == "VT-09":
        return {
            "Just County Names": scenario["unit"],
            "Docket Number": scenario["case_number"],
            "Plaintiff": scenario["plaintiff"],
            "Defendant": scenario["defendant"],
            "Motion": scenario["motion_title"],
            "1": scenario["moving_party"],
            "3": scenario["request"],
            "4": scenario["reason"],
            "13": signed,
            "14": f"/s/ {scenario['moving_party']}",
            "15": scenario["moving_party"],
            "16": "41 Linden Lane, Barre, VT 05641",
        }
    if form_id == "VT-10":
        return {
            "Unit": scenario["unit"],
            "Docket Number": scenario["case_number"],
            "Plaintiff": scenario["plaintiff"],
            "Defendant": scenario["defendant"],
            "10": date(scenario["existing_order_date"]),
            "15": scenario["children"][0]["name"],
            "16": date(scenario["children"][0]["dob"]),
            "56": scenario["changed_circumstances"],
            "70a": scenario["changed_circumstances"],
            "71": signed,
            "71a": f"/s/ {scenario['moving_party']}",
            "71b": scenario["moving_party"],
        }
    raise KeyError(f"No fill rules for {form_id}")


def checkbox_rules(form_id: str) -> dict[str, str]:
    names: dict[str, list[str]] = {
        "IL-01": [
            "24 - Pay Me Money",
            "29 - Pay cost of this lawsuit checkbox",
            "Last - Completing this form myself checkbox2",
        ],
        "IL-03": [
            "2a - Checkbox",
            "3a - Checkbox",
            "4a - Checkbox",
            "4b - Checkbox",
            "4c - Checkbox",
        ],
        "IL-04": ["4 - Checkbox"],
        "IL-08": ["Last - Completing this form myself checkbox"],
        "MA-01": [
            "form1[0].#subform[0].CheckBox1[0]",
            "form1[0].#subform[0].CheckBox1[2]",
        ],
        "MA-02": [
            "form1[0].BodyPage1[0].#subform[0].CheckBox1[0]",
            "form1[0].BodyPage1[0].#subform[0].CheckBox1[1]",
        ],
        "MA-04": [
            "form1[0].USPage1[0].CheckBox1[0]",
            "form1[0].USPage1[0].CheckBox1[2]",
        ],
        "MA-05": [
            "form1[0].BodyPage1[0].S4[0].CheckBox1[1]",
            "form1[0].BodyPage1[0].S8[0].CheckBox1[0]",
        ],
        "MA-06": ["form1[0].#pageSet[0].Page1[0].Yes_chkbox[0]"],
        "MA-08": [
            "form1[0].#subform[0].CheckBox10[0]",
            "form1[0].#subform[0].CheckBox3[0]",
            "form1[0].#subform[0].CheckBox6[0]",
        ],
        "MA-10": ["form1[0].#subform[0].CheckBox1[0]"],
        "VT-08": ["CB4a"],
    }
    checked_value = "/1" if form_id.startswith("MA-") else "/Yes"
    return {name: checked_value for name in names.get(form_id, [])}


def set_checkbox_states(writer: PdfWriter, states: dict[str, str]) -> None:
    """Set widget appearance states, including forms pypdf cannot regenerate."""
    remaining = set(states)
    for page in writer.pages:
        for reference in page.get("/Annots") or []:
            annotation = reference.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            parts: list[str] = []
            current = annotation
            ancestors = [current]
            while current:
                if current.get("/T") is not None:
                    parts.append(str(current["/T"]))
                parent = current.get("/Parent")
                current = parent.get_object() if parent else None
                if current:
                    ancestors.append(current)
            qualified_name = ".".join(reversed(parts))
            if qualified_name not in states:
                continue
            state = NameObject(states[qualified_name])
            annotation[NameObject("/AS")] = state
            for ancestor in ancestors:
                ancestor[NameObject("/V")] = state
            remaining.discard(qualified_name)
    if remaining:
        raise KeyError(f"Could not find checkbox widgets: {sorted(remaining)}")


def overlay_ma07(template: Path, destination: Path, scenario: dict[str, Any]) -> None:
    packet = io.BytesIO()
    pdf = canvas.Canvas(packet, pagesize=(604.113, 781.854))
    pdf.setFont("Helvetica", 8)
    values = [
        (75, 640, "Boston"),
        (665 - 604, 640, ""),
        (470, 611, date(scenario["entry_date"])),
        (45, 524, scenario["tenant"]),
        (65, 494, split_address(scenario["premises"])[0]),
        (350, 494, split_address(scenario["premises"])[1]),
        (510, 494, split_address(scenario["premises"])[3]),
        (120, 383, scenario["landlord"]),
        (350, 383, split_address(scenario["landlord_address"])[0]),
        (65, 351, split_address(scenario["landlord_address"])[1]),
        (175, 351, split_address(scenario["landlord_address"])[3]),
        (410, 351, scenario["premises"]),
        (30, 287, scenario["termination_reason"]),
        (100, 254, scenario["rent_owed"]),
        (25, 153, f"/s/ {scenario['landlord']}"),
        (25, 123, date(scenario["signed_date"])),
        (340, 153, scenario["landlord_address"]),
    ]
    for x, y, value in values:
        pdf.drawString(x, y, str(value))
    pdf.save()
    packet.seek(0)
    base = PdfReader(template)
    layer = PdfReader(packet)
    writer = PdfWriter()
    for index, page in enumerate(base.pages):
        if index == 0:
            page.merge_page(layer.pages[0])
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Subject": "LITEFile fictional benchmark fixture using an official court template"
        }
    )
    with destination.open("wb") as output:
        writer.write(output)


def overlay_ma10(template: Path, destination: Path, scenario: dict[str, Any]) -> None:
    packet = io.BytesIO()
    pdf = canvas.Canvas(packet, pagesize=(612, 792))
    pdf.setFont("Helvetica", 8)
    values = [
        (165, 760, scenario["docket_number"]),
        (165, 733, "Somerville"),
        (30, 688, scenario["plaintiff"]),
        (30, 661, scenario["plaintiff_address"]),
        (318, 688, scenario["defendant"]),
        (318, 661, scenario["defendant_address"]),
        (66, 535, scenario["plaintiff"]),
        (237, 508, scenario["defendant"]),
        (525, 508, scenario["principal_due"].replace("$", "")),
        (192, 481, scenario["interest"].replace("$", "")),
        (498, 454, scenario["principal_due"].replace("$", "")),
        (57, 346, scenario["basis"]),
        (55, 218, date(scenario["signed_date"])),
        (318, 202, f"/s/ {scenario['plaintiff']}"),
        (345, 175, scenario["plaintiff"]),
        (336, 121, scenario["plaintiff_address"]),
    ]
    for x, y, value in values:
        pdf.drawString(x, y, str(value))
    pdf.save()
    packet.seek(0)
    base = PdfReader(template)
    layer = PdfReader(packet)
    writer = PdfWriter()
    writer.clone_document_from_reader(base)
    writer.pages[0].merge_page(layer.pages[0])
    writer.add_metadata(
        {
            "/Subject": "LITEFile fictional benchmark fixture using an official court template"
        }
    )
    with destination.open("wb") as output:
        writer.write(output)


def fill_form(
    template: Path, destination: Path, form_id: str, scenario: dict[str, Any]
) -> None:
    if form_id == "MA-07":
        overlay_ma07(template, destination, scenario)
        return
    if form_id == "MA-10":
        overlay_ma10(template, destination, scenario)
        return
    reader = PdfReader(template)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    values = common_rules(form_id, scenario) | checkbox_rules(form_id)
    fields = reader.get_fields() or {}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise KeyError(f"{form_id} fill rules reference unknown fields: {unknown}")
    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False)
    set_checkbox_states(writer, checkbox_rules(form_id))
    writer.add_metadata(
        {
            "/Subject": "LITEFile fictional benchmark fixture using an official court template"
        }
    )
    with destination.open("wb") as output:
        writer.write(output)


def flatten(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(".pdf.tmp")
    subprocess.run(
        [
            "gs",
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            f"-sOutputFile={temporary}",
            str(source),
        ],
        check=True,
    )
    temporary.replace(destination)


def write_extractability_summaries(records: list[dict[str, Any]]) -> None:
    """Keep the CSV and Markdown views aligned with extractability.jsonl."""
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(
        [
            "id",
            "jurisdiction",
            "form_name",
            "interactive_pdf",
            "flattened_pdf",
            "direct_fields",
            "semantic_fields",
            "optional_inferences",
            "do_not_require",
        ]
    )
    for record in records:
        writer.writerow(
            [
                record["id"],
                record["jurisdiction"],
                record["form_name"],
                record["interactive_pdf"],
                record["flattened_pdf"],
                "; ".join(record["directly_visible_or_labeled"]),
                "; ".join(record["semantic_but_reasonable"]),
                "; ".join(record["optional_inferences"]),
                "; ".join(record["do_not_require"]),
            ]
        )
    (ROOT / "extractability.csv").write_text(csv_buffer.getvalue())

    jurisdiction_names = {
        "massachusetts": "Massachusetts",
        "vermont": "Vermont",
        "illinois": "Illinois",
    }
    lines = [
        "# LITEFile PDF extractability guide",
        "",
        "These are pragmatic test expectations, not gold labels. `Direct` means the PDF visibly supplies the value. `Semantic` means LITEFile should usually be able to infer it from the document title, division, or filing language. `Do not require` identifies fields where abstention is a valid outcome.",
    ]
    for jurisdiction, heading in jurisdiction_names.items():
        lines.extend(
            [
                "",
                f"## {heading}",
                "",
                "| ID | Form | Direct | Semantic | Optional | Do not require |",
                "|---|---|---|---|---|---|",
            ]
        )
        for record in records:
            if record["jurisdiction"] != jurisdiction:
                continue
            columns = [
                record["id"],
                record["form_name"],
                ", ".join(record["directly_visible_or_labeled"]) or "-",
                ", ".join(record["semantic_but_reasonable"]) or "-",
                ", ".join(record["optional_inferences"]) or "-",
                ", ".join(record["do_not_require"]) or "-",
            ]
            lines.append("| " + " | ".join(columns) + " |")
    (ROOT / "extractability.md").write_text("\n".join(lines) + "\n")


def sync_metadata() -> None:
    sources = json.loads((ROOT / "official_sources.json").read_text())
    for filename in (
        "paired_manifest.jsonl",
        "seed_manifest.jsonl",
        "extractability.jsonl",
    ):
        path = ROOT / filename
        records = [
            reconcile_official_template(clean(json.loads(line)))
            for line in path.read_text().splitlines()
        ]
        if filename == "paired_manifest.jsonl":
            for record in records:
                record["official_pdf_url"] = sources[record["id"]]
                record["official_template"] = f"official_templates/{record['id']}.pdf"
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        )
        if filename == "extractability.jsonl":
            write_extractability_summaries(records)
    motion_path = ROOT / "motion_cases.jsonl"
    motion_records = [
        clean(json.loads(line)) for line in motion_path.read_text().splitlines()
    ]
    for record in motion_records:
        record["uses_official_template"] = True
        record["official_template"] = f"official_templates/{record['id']}.pdf"
        record["official_pdf_url"] = sources[record["id"]]
    motion_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n" for record in motion_records
        )
    )


def write_structure_report() -> None:
    report: list[dict[str, Any]] = []
    for variant, directory in (("interactive", INTERACTIVE), ("flattened", FLATTENED)):
        for path in sorted(directory.glob("*.pdf")):
            reader = PdfReader(path)
            report.append(
                {
                    "id": path.stem,
                    "variant": variant,
                    "pages": len(reader.pages),
                    "acroform_fields": len(reader.get_fields() or {}),
                    "text_chars": sum(
                        len(page.extract_text() or "") for page in reader.pages
                    ),
                }
            )
    (ROOT / "pdf_structure_check.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "ids",
        nargs="*",
        help="Corpus IDs to build; omit to build every downloaded template",
    )
    parser.add_argument(
        "--sync-metadata",
        action="store_true",
        help="Clean visible fixture artifacts in manifests and refresh the PDF structure report",
    )
    args = parser.parse_args()
    records = {
        record["id"]: clean(record)
        for record in (json.loads(line) for line in MANIFEST.read_text().splitlines())
    }
    selected = args.ids or sorted(records)
    INTERACTIVE.mkdir(parents=True, exist_ok=True)
    FLATTENED.mkdir(parents=True, exist_ok=True)
    for form_id in selected:
        template = TEMPLATES / f"{form_id}.pdf"
        if not template.exists():
            print(f"skip {form_id}: official template has not downloaded")
            continue
        interactive = INTERACTIVE / f"{form_id}.pdf"
        flattened = FLATTENED / f"{form_id}.pdf"
        print(f"build {form_id}")
        fill_form(template, interactive, form_id, records[form_id]["scenario"])
        flatten(interactive, flattened)
        if form_id in MOTION_OUTPUTS:
            shutil.copyfile(interactive, ROOT / "motions" / MOTION_OUTPUTS[form_id])
    if args.sync_metadata:
        sync_metadata()
        write_structure_report()


if __name__ == "__main__":
    main()
