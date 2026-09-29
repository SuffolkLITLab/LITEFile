from decimal import Decimal
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


def test_static_zero_and_unknown_do_not_become_a_false_total():
    documents = [
        SimpleNamespace(filing_type_code="zero", filing_type_name="Order", name="a"),
        SimpleNamespace(filing_type_code="missing", filing_type_name="Motion", name="b", role="supporting"),
    ]
    draft = SimpleNamespace(
        jurisdiction="vermont",
        court_code="court",
        case_type_code="sc",
        case_category_code="civil",
        existing_case="existing",
        case_type_name="Small Claims",
        documents=SimpleNamespace(all=lambda: documents),
        amount_in_controversy="100",
    )
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "zero", "fee": 0}]):
        result = estimate_fees(draft)
    assert result["total"] == ""
    assert result["rows"][0]["amount"] == "~$0.00"
    assert result["rows"][1]["amount"] == "Not available yet"


def test_zero_listed_fee_uses_a_matching_estimate():
    document = SimpleNamespace(filing_type_code="complaint", filing_type_name="Complaint", name="a", role="lead")
    draft = SimpleNamespace(
        jurisdiction="vermont",
        court_code="court",
        case_type_code="sc",
        case_category_code="civil",
        existing_case="new",
        case_type_name="Small Claims",
        documents=SimpleNamespace(all=lambda: [document]),
        amount_in_controversy="100",
    )
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "complaint", "fee": "0.00"}]):
        assert estimate_fees(draft)["total"] == "~$65.00"


@pytest.mark.parametrize("state", ["illinois", "massachusetts", "vermont"])
def test_static_fee_takes_precedence_and_missing_code_stays_unknown(state):
    document = SimpleNamespace(filing_type_code="complaint", filing_type_name="Complaint", name="a", role="lead")
    draft = SimpleNamespace(
        jurisdiction=state,
        court_code="court",
        case_type_code="sc",
        case_category_code="civil",
        existing_case="new",
        case_type_name="Small Claims",
        documents=SimpleNamespace(all=lambda: [document]),
        amount_in_controversy="100",
    )
    with patch("efile.services.fee_estimates._codes", return_value=[{"code": "complaint", "fee": "123.45"}]):
        assert estimate_fees(draft)["total"] == "~$123.45"
    draft.existing_case = "existing"
    with patch("efile.services.fee_estimates._codes", return_value=[]):
        assert estimate_fees(draft)["total"] == ""
