"""Exercise source disagreements and AOIC markup with small input workbooks."""

import importlib.util
from pathlib import Path

import openpyxl
import pytest

spec = importlib.util.spec_from_file_location(
    "contacts", Path(__file__).parents[1] / "build_illinois_court_contacts.py"
)
contacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contacts)


def workbook(tmp_path, records):
    book = openpyxl.Workbook()
    book.active.append(
        ["court_code", "name", "tyler_court_code", "address_county", "phone"]
    )
    for row in records:
        book.active.append(row)
    path = tmp_path / "courts.xlsx"
    book.save(path)
    return path


def test_split_and_empty_headings_preserve_county_identity():
    assert contacts.official_phones(
        "<strong>Cumberland</strong><strong></strong><br>Phone: 217/849-3601<br>"
        "<strong>Rock </strong><strong>Island</strong><br>Phone: 309/558-3538"
    ) == {"cumberland": "2178493601", "rockisland": "3095583538"}


def test_official_clerk_number_wins_and_discrepancy_is_preserved(tmp_path):
    path = workbook(tmp_path, [("clerk", "Lake court", "lake", "Lake", "847-377-3600")])
    result, audit = contacts.build(
        path,
        [{"code": "lake", "name": "Lake County"}],
        "<strong>Lake</strong>Phone: 847/377-3380",
    )
    assert (
        result["court_specific_requirements"]["lake"]["contact"]["phone"]
        == "847-377-3380"
    )
    assert audit[0][4:6] == ["847-377-3600", "8473773380"]
    assert "differs from ILAO" in audit[0][-1]


@pytest.mark.parametrize(
    "kind", ["duplicate", "wrong_county", "unknown_code", "missing_phone"]
)
def test_ambiguous_or_unverified_records_are_withheld(tmp_path, kind):
    records = [("clerk", "Lake court", "lake", "Lake", "847-377-3600")]
    courts = [{"code": "lake", "name": "Lake County"}]
    html = "<strong>Lake</strong>Phone: 847/377-3380"
    if kind == "duplicate":
        records *= 2
    elif kind == "wrong_county":
        courts[0]["name"] = "Cook County"
    elif kind == "unknown_code":
        courts = []
    else:
        html = "<strong>Lake</strong>Phone: unknown"
    result, _ = contacts.build(workbook(tmp_path, records), courts, html)
    assert result["court_specific_requirements"] == {}


def test_cook_divisions_keep_explicit_county_wide_contact(tmp_path):
    result, audit = contacts.build(
        workbook(
            tmp_path, [("cook-building", "Courthouse", None, "Cook", "312-000-0000")]
        ),
        [{"code": code, "name": code} for code in ["cook:cd1", "cook:dr1"]],
        "<strong>Cook</strong>Phone: 312/603-5030",
    )
    assert len(result["court_specific_requirements"]) == 2
    for entry in result["court_specific_requirements"].values():
        assert entry["contact"]["phone"] == "312-603-5030"
        assert entry["contact"]["name"] == "Cook County Circuit Clerk customer service"
    assert audit[0][-1].startswith("unmapped")


def test_duplicate_official_entries_fail_closed():
    with pytest.raises(ValueError, match="Duplicate"):
        contacts.official_phones(
            "<strong>Lake</strong>Phone: 847/377-3380<strong>Lake</strong>Phone: 847/377-3600"
        )


def test_leading_country_code_is_not_truncated_into_a_wrong_phone():
    assert contacts.digits("1-847-377-3380") == "8473773380"
