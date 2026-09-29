import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from efile.services.fee_estimates import contingent_fee, estimate_fees, money
from efile.utils.config_loader import config_loader


@pytest.mark.parametrize(
    ("state", "amount", "low", "high"),
    [
        ("illinois", "2500", "114", "270"),
        ("illinois", "2500.01", "266", "362"),
        ("illinois", "10000.01", None, None),
        ("massachusetts", "500", "40", "40"),
        ("massachusetts", "500.01", "50", "50"),
        ("massachusetts", "2000", "50", "50"),
        ("massachusetts", "2000.01", "100", "100"),
        ("massachusetts", "5000", "100", "100"),
        ("massachusetts", "5000.01", "150", "150"),
        ("vermont", "1000", "65", "65"),
        ("vermont", "1000.01", "90", "90"),
        ("vermont", "", "65", "90"),
    ],
)
def test_claim_bands(state, amount, low, high):
    draft = SimpleNamespace(existing_case="new", case_type_name="Small Claims", amount_in_controversy=amount)
    document = SimpleNamespace(role="lead", filing_type_name="Complaint")
    rules = config_loader.load_jurisdiction_config(state)["fee_estimates"]["rules"]
    result = contingent_fee(draft, document, rules)
    assert result == ((Decimal(low), Decimal(high)) if low is not None else None)


@pytest.mark.parametrize("amount,fee", [("500", "25"), ("500.01", "35")])
def test_vermont_counterclaim_has_its_own_schedule(amount, fee):
    draft = SimpleNamespace(existing_case="existing", case_type_name="Small Claims", amount_in_controversy=amount)
    document = SimpleNamespace(role="supporting", filing_type_name="Counterclaim")
    rules = config_loader.load_jurisdiction_config("vermont")["fee_estimates"]["rules"]
    assert contingent_fee(draft, document, rules) == (Decimal(fee), Decimal(fee))
    document.filing_type_name = "Motion"
    assert contingent_fee(draft, document, rules) is None


@pytest.mark.parametrize("value", ["", None, "NaN", "Infinity", "-10", "unknown"])
def test_invalid_fee_is_unknown_not_zero(value):
    assert money(value) is None


SAMPLES = json.loads((Path(__file__).parent / "fixtures" / "fee_code_samples.json").read_text())
NO_AMOUNTS = dict.fromkeys(("amountincontroversy", "civilclaimamount", "probateestateamount"), "Not Available")


def make_draft(state="illinois", phase="existing", name="Unfamiliar filing", case_name="Unfamiliar case"):
    document = SimpleNamespace(filing_type_code="filing", filing_type_name=name, name="file.pdf", role="lead")
    draft = SimpleNamespace(
        jurisdiction=state,
        selected_payment_account_type="BankAccount",
        court_code="court",
        case_type_code="case",
        case_category_code="category",
        existing_case=phase,
        case_type_name=case_name,
        amount_in_controversy="",
        documents=SimpleNamespace(all=lambda: [document]),
    )
    return draft, document


def code_lookup(filings, case_types=()):
    def lookup(_state, path, **_kwargs):
        return list(case_types) if path.endswith("case_types/") else filings

    return lookup


@pytest.mark.parametrize("sample", SAMPLES["samples"], ids=lambda sample: sample["id"])
def test_live_code_samples_across_three_states(sample):
    draft, _ = make_draft(sample["jurisdiction"], "new", case_name=sample["case_type"]["name"])
    draft.court_code = sample["court"]
    draft.case_category_code = sample["category"]
    draft.case_type_code = sample["case_type"]["code"]
    documents = [
        SimpleNamespace(
            filing_type_code=row["code"],
            filing_type_name=row["name"],
            name="file.pdf",
            role="lead" if index == 0 else "supporting",
        )
        for index, row in enumerate(sample["filings"])
    ]
    draft.documents = SimpleNamespace(all=lambda: documents)
    with patch(
        "efile.services.fee_estimates._codes", side_effect=code_lookup(sample["filings"], [sample["case_type"]])
    ) as codes:
        result = estimate_fees(draft)
    base = Decimal(sample["expected"])
    state = sample["jurisdiction"]
    platform = Decimal("22") if state == "massachusetts" else (Decimal("14") if state == "vermont" else Decimal("0"))
    expected = base + platform
    if expected:
        expected += Decimal("1") if state == "vermont" else Decimal("0.25")
    assert result["total"] == f"~${expected:.2f}"
    assert result["is_zero"] == (expected == 0)
    assert result["rows"][0]["label"] == "Case opening fee"
    assert sum(row["label"] == "Case opening fee" for row in result["rows"]) == 1
    assert codes.call_args_list[1].kwargs["category_id"] == sample["category"]


@pytest.mark.parametrize("state", ["illinois", "massachusetts", "vermont"])
def test_state_convenience_fee_is_included_with_zero_court_fees(state):
    draft, _ = make_draft(state, "new")
    filings = [{"code": "filing", "fee": "", **NO_AMOUNTS}]
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup(filings, [{"code": "case", "initial": True, "fee": 0}]),
    ):
        result = estimate_fees(draft)
        assert result["is_zero"] is (state != "massachusetts")
        assert result["total"] == ("~$22.25" if state == "massachusetts" else "~$0.00")


@pytest.mark.parametrize("row", SAMPLES["illinois_answers"], ids=lambda row: row["code"])
def test_illinois_answers_and_appearances_use_selected_code_not_name(row):
    draft, document = make_draft()
    document.filing_type_code = row["code"]
    document.filing_type_name = row["name"]
    with patch("efile.services.fee_estimates._codes", side_effect=code_lookup([row])) as codes:
        result = estimate_fees(draft)
    assert result["total"] == ("~$186.25" if row["fee"] else "~$0.00")
    assert codes.call_count == 1  # Never charge the case opening fee again.


@pytest.mark.parametrize("field", list(NO_AMOUNTS))
@pytest.mark.parametrize("fee", ["", "0.00", "10.00"])
@pytest.mark.parametrize("phase", ["new", "existing"])
@pytest.mark.parametrize("amount", ["", "5000"])
def test_amount_dependent_fees_never_become_false_zero(field, fee, phase, amount):
    draft, _ = make_draft(phase=phase)
    draft.amount_in_controversy = amount
    row = {"code": "filing", "fee": fee, **NO_AMOUNTS, field: "Required"}
    case_type = {"code": "case", "initial": True, "fee": 0}
    with patch("efile.services.fee_estimates._codes", side_effect=code_lookup([row], [case_type])):
        result = estimate_fees(draft)
    assert result["total"] == ""
    assert result["is_zero"] is False


@pytest.mark.parametrize(
    "amount,expected", [("", "$114.25–$362.25"), ("1000", "$114.25–$270.25"), ("3000", "$266.25–$362.25")]
)
def test_real_cook_amount_flag_uses_configured_range_instead_of_zero(amount, expected):
    draft, document = make_draft(phase="new", case_name="Small Claims")
    row = SAMPLES["amount_dependent"]
    document.filing_type_code = row["code"]
    document.filing_type_name = row["name"]
    draft.amount_in_controversy = amount
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup([row], [{"code": "case", "fee": 0, "initial": True}]),
    ):
        result = estimate_fees(draft)
    assert result["total"] == expected
    assert result["is_zero"] is False
    assert "Included in the case opening estimate" in result["rows"][1]["note"]


def test_estate_input_does_not_use_amount_in_controversy_bands():
    draft, _ = make_draft(phase="new", name="Complaint", case_name="Small Claims")
    row = {"code": "filing", "fee": "0.00", **NO_AMOUNTS, "probateestateamount": "Required"}
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup([row], [{"code": "case", "fee": 0, "initial": True}]),
    ):
        assert estimate_fees(draft)["total"] == ""


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"code": "filing"},
        {"code": "filing", "fee": ""},
        {"code": "filing", "fee": "0.00"},
        {"code": "filing", "fee": "garbage", **NO_AMOUNTS},
    ],
)
def test_missing_or_incomplete_codes_remain_unknown(row):
    draft, _ = make_draft(name="Answer")
    with patch("efile.services.fee_estimates._codes", side_effect=code_lookup([row])):
        result = estimate_fees(draft)
    assert result["is_zero"] is False
    assert result["total"] == ""


@pytest.mark.parametrize(
    "case_type", [{}, {"code": "case", "fee": 0, "initial": False}, {"code": "case", "fee": None, "initial": True}]
)
def test_missing_or_noninitial_case_fee_cannot_make_new_case_free(case_type):
    draft, _ = make_draft(phase="new")
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup([{"code": "filing", "fee": "", **NO_AMOUNTS}], [case_type]),
    ):
        assert estimate_fees(draft)["is_zero"] is False


def test_extra_document_fee_is_added_to_entry_fee_once():
    draft, first = make_draft(phase="new")
    second = SimpleNamespace(
        filing_type_code="jury", filing_type_name="Jury demand", name="jury.pdf", role="supporting"
    )
    draft.documents = SimpleNamespace(all=lambda: [first, second])
    rows = [{"code": "filing", "fee": "", **NO_AMOUNTS}, {"code": "jury", "fee": "212.50", **NO_AMOUNTS}]
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup(rows, [{"code": "case", "initial": True, "fee": 256}]),
    ):
        assert estimate_fees(draft)["total"] == "~$468.75"


def test_unknown_document_keeps_total_unknown():
    draft, first = make_draft(phase="new")
    second = SimpleNamespace(filing_type_code="missing", filing_type_name="Other", name="other.pdf", role="supporting")
    draft.documents = SimpleNamespace(all=lambda: [first, second])
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup(
            [{"code": "filing", "fee": "", **NO_AMOUNTS}], [{"code": "case", "initial": True, "fee": 0}]
        ),
    ):
        assert estimate_fees(draft)["total"] == ""


def test_no_documents_are_not_a_free_filing():
    draft, _ = make_draft()
    draft.documents = SimpleNamespace(all=lambda: [])
    with patch("efile.services.fee_estimates._codes", return_value=[]):
        assert estimate_fees(draft)["is_zero"] is False


def test_saved_required_amount_flag_blocks_zero_even_if_code_flags_disagree():
    draft, document = make_draft()
    document.filing_requires_amount_in_controversy = True
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "filing", "fee": "0.00", **NO_AMOUNTS}]):
        assert estimate_fees(draft)["is_zero"] is False


def test_amount_above_supported_schedule_stays_unknown():
    draft, document = make_draft(phase="new", case_name="Small Claims")
    row = SAMPLES["amount_dependent"]
    document.filing_type_code = row["code"]
    document.filing_type_name = row["name"]
    draft.amount_in_controversy = "10001"
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup([row], [{"code": "case", "fee": 0, "initial": True}]),
    ):
        result = estimate_fees(draft)
    assert result["is_zero"] is False
    assert result["total"] == ""


def test_optional_monetary_input_is_not_proof_of_a_free_filing():
    draft, _ = make_draft()
    row = {"code": "filing", "fee": "0.00", **NO_AMOUNTS, "amountincontroversy": "Optional"}
    with patch("efile.services.fee_estimates._codes", return_value=[row]):
        assert estimate_fees(draft)["is_zero"] is False


@pytest.mark.parametrize("phase", ["new", "existing"])
def test_convenience_fee_is_added_once_for_multiple_documents(phase):
    draft, lead = make_draft(phase=phase)
    other = SimpleNamespace(filing_type_code="other", filing_type_name="Other", name="other.pdf", role="supporting")
    draft.documents = SimpleNamespace(all=lambda: [lead, other])
    rows = [{"code": code, "fee": "10", **NO_AMOUNTS} for code in ("filing", "other")]
    with patch(
        "efile.services.fee_estimates._codes",
        side_effect=code_lookup(rows, [{"code": "case", "initial": True, "fee": 0}]),
    ):
        result = estimate_fees(draft)
    assert result["total"] == "~$20.25"
    assert result["rows"][-1]["label"] == "Processing fee"
    assert sum(row["label"] == "Processing fee" for row in result["rows"]) == 1
    assert result["is_zero"] is False


@pytest.mark.parametrize(
    "configured,expected", [(None, "~$0.00"), ("0.00", "~$0.00"), ("0.50", "~$0.50"), ("invalid", "")]
)
def test_convenience_fee_is_optional_and_configurable(configured, expected):
    draft, _ = make_draft("vermont")
    with (
        patch(
            "efile.services.fee_estimates.config_loader.load_jurisdiction_config",
            return_value={
                "fee_estimates": {
                    "surcharges": {
                        "payment_methods": {"BankAccount": {"fixed": configured, "only_when_amount_due": False}}
                    }
                }
            }
            if configured is not None
            else {},
        ),
        patch("efile.services.fee_estimates._codes", return_value=[{"code": "filing", "fee": "", **NO_AMOUNTS}]),
    ):
        result = estimate_fees(draft)
    assert result["total"] == expected


def test_convenience_fee_does_not_turn_unknown_fees_into_a_known_total():
    draft, _ = make_draft()
    with patch("efile.services.fee_estimates._codes", return_value=[]):
        result = estimate_fees(draft)
    assert result["rows"][-1]["amount"] == "Not available yet"
    assert result["total"] == ""
    assert result["partial"] is True
    assert result["is_zero"] is False


def test_selected_services_are_itemized_and_included_before_card_processing():
    draft, document = make_draft()
    draft.selected_payment_account_type = "CC"
    document.requested_optional_services = ["copy", "mail"]

    def lookup(_state, path, **_kwargs):
        if path.endswith("/optional_services"):
            return [
                {"code": "copy", "name": "Certified copy", "fee": "12.50"},
                {"code": "mail", "name": "Mail service", "fee": "5"},
                {"code": "unused", "name": "Not selected", "fee": "100"},
            ]
        return [{"code": "filing", "fee": "100", **NO_AMOUNTS}]

    with patch("efile.services.fee_estimates._codes", side_effect=lookup):
        result = estimate_fees(draft)
    assert result["total"] == "~$120.90"  # $117.50 + 2.89%, rounded to cents.
    assert [row["label"] for row in result["rows"]] == [
        "Unfamiliar filing",
        "Certified copy",
        "Mail service",
        "Processing fee",
    ]
    assert result["rows"][1]["amount"] == "~$12.50"
    assert not any(row.get("document_name") for row in result["rows"])


@pytest.mark.parametrize("service", [{}, {"fee": ""}, {"fee": "invalid"}, {"fee": "0", "hasfeeprompt": "true"}])
def test_unknown_optional_service_cost_prevents_false_free_total(service):
    draft, document = make_draft()
    document.requested_optional_services = ["extra"]

    def lookup(_state, path, **_kwargs):
        if path.endswith("/optional_services"):
            return [{"code": "extra", **service}] if service else []
        return [{"code": "filing", "fee": "0", **NO_AMOUNTS}]

    with patch("efile.services.fee_estimates._codes", side_effect=lookup):
        result = estimate_fees(draft)
    assert result["partial"] is True
    assert result["is_zero"] is False
    assert result["total"] == ""


def test_services_are_charged_per_document_with_one_lookup_per_filing_type():
    draft, first = make_draft()
    first.requested_optional_services = ["copy"]
    second = SimpleNamespace(**vars(first))
    second.name = "second.pdf"
    second.role = "supporting"
    second.requested_optional_services = [{"code": "copy", "multiplier": 3}]
    draft.documents = SimpleNamespace(all=lambda: [first, second])

    def lookup(_state, path, **_kwargs):
        if path.endswith("/optional_services"):
            return [{"id": "copy", "label": "Copy", "cost": "2", "multiplier": True}]
        return [{"code": "filing", "fee": "0", **NO_AMOUNTS}]

    with patch("efile.services.fee_estimates._codes", side_effect=lookup) as codes:
        result = estimate_fees(draft)
    assert result["total"] == "~$8.25"
    assert codes.call_count == 2
    assert result["rows"][3]["label"] == "Copy × 3"
    assert result["rows"][1]["document_name"] == "file.pdf"
    assert result["rows"][3]["document_name"] == "second.pdf"


def test_explicit_zero_service_price_is_known():
    draft, document = make_draft()
    document.requested_optional_services = ["free"]

    def lookup(_state, path, **_kwargs):
        if path.endswith("/optional_services"):
            return [{"code": "free", "fee": 0}]
        return [{"code": "filing", "fee": "0", **NO_AMOUNTS}]

    with patch("efile.services.fee_estimates._codes", side_effect=lookup):
        result = estimate_fees(draft)
    assert result["total"] == "~$0.00"
    assert result["is_zero"] is True


def test_saved_waiver_account_does_not_price_the_pre_waiver_estimate():
    # A filer who chose the waiver, went to Review and came back.
    draft, _document = make_draft()
    draft.selected_payment_account_type = "WV"
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "filing", "fee": "100", **NO_AMOUNTS}]):
        result = estimate_fees(draft)
    draft.selected_payment_account_type = ""
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "filing", "fee": "100", **NO_AMOUNTS}]):
        unsaved = estimate_fees(draft)
    assert result == unsaved
    assert result["total"]
    assert "waiver account" not in result["note"]
