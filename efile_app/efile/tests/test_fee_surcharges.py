from decimal import Decimal
from types import SimpleNamespace

import pytest

from efile.services.fee_surcharges import surcharge_estimate
from efile.utils.config_loader import config_loader


def estimate(state, base, method="", phase="new", name="Civil case", **context):
    draft = SimpleNamespace(selected_payment_account_type=method, existing_case=phase, case_type_name=name)
    policy = config_loader.load_jurisdiction_config(state)["fee_estimates"]["surcharges"]
    bounds = None if base is None else (Decimal(str(base)), Decimal(str(base)))
    return surcharge_estimate(policy, draft, bounds, **context)


@pytest.mark.parametrize(
    "state,base,method,name,total",
    [
        ("illinois", 0, "BankAccount", "Civil No Contact Order", "0"),
        ("illinois", 256, "BankAccount", "Eviction", "256.25"),
        ("illinois", 256, "CC", "Eviction", "263.40"),
        ("vermont", 0, "CC", "Relief from Abuse", "14.40"),
        ("vermont", 295, "CC", "Divorce", "317.93"),
        ("vermont", 295, "BankAccount", "Divorce", "310"),
        ("massachusetts", 195, "BankAccount", "Money action", "217.25"),
        ("massachusetts", 195, "CC", "Money action", "223.27"),
    ],
)
def test_published_rules_and_observed_quotes(state, base, method, name, total):
    _, bounds, _ = estimate(state, base, method, name=name)
    assert bounds == (Decimal(total), Decimal(total))


def test_unknown_method_uses_range_without_waiver_assumption():
    _, bounds, notes = estimate("massachusetts", 195)
    assert bounds == (Decimal("217.25"), Decimal("223.27"))
    assert "payment method" in " ".join(notes)


@pytest.mark.parametrize(
    "first_use,expected", [(True, ("317.93", "317.93")), (False, ("303.53", "303.53")), (None, ("303.53", "317.93"))]
)
def test_vermont_existing_case_first_use(first_use, expected):
    _, bounds, _ = estimate("vermont", 295, "CC", phase="existing", first_use=first_use)
    assert bounds == tuple(map(Decimal, expected))


def test_massachusetts_subsequent_filing_has_no_platform_fee():
    assert estimate("massachusetts", 100, "BankAccount", phase="existing")[1] == (Decimal("100.25"),) * 2


def test_vermont_automatic_zero_fee_exemption_and_statutory_exception():
    assert estimate("vermont", 0, "CC")[1] == (Decimal("0"),) * 2
    rows, bounds, notes = estimate("vermont", 0, "CC", name="Relief from Abuse")
    assert bounds == (Decimal("14.40"),) * 2
    assert "do not need to qualify based on income" in " ".join(notes)


def test_waiver_selection_does_not_establish_final_zero():
    _, bounds, notes = estimate("vermont", 0, "WV", name="Relief from Abuse")
    assert bounds is None
    assert "court must confirm" in " ".join(notes)


def test_explicit_government_exemption_still_requires_waiver_account():
    assert estimate("vermont", 100, "CC", exemption="government_or_appointed")[1] == (Decimal("117.29"),) * 2
    assert estimate("vermont", 100, "WV", exemption="government_or_appointed")[1] is None


@pytest.mark.parametrize("state", ["illinois", "massachusetts", "vermont"])
def test_unknown_court_fee_remains_unknown(state):
    assert estimate(state, None, "BankAccount")[1] is None


def test_configurable_percentage_basis_fixed_fee_and_zero_behavior():
    draft = SimpleNamespace(selected_payment_account_type="test", existing_case="new", case_type_name="")
    policy = {
        "platform": {"amount": "10"},
        "payment_methods": {"test": {"fixed": "2", "percent": "3", "basis": "court", "only_when_amount_due": False}},
    }
    assert surcharge_estimate(policy, draft, (Decimal("100"),) * 2)[1] == (Decimal("115"),) * 2
    policy["platform"]["amount"] = "0"
    assert surcharge_estimate(policy, draft, (Decimal("0"),) * 2)[1] == (Decimal("2"),) * 2
    policy["payment_methods"]["test"]["percent"] = "NaN"
    assert surcharge_estimate(policy, draft, (Decimal("0"),) * 2)[1] is None


def test_free_response_does_not_prove_vermont_platform_fee_was_paid():
    assert estimate("vermont", 0, "CC", phase="existing")[1] == (Decimal("0"), Decimal("14.40"))
    assert estimate("vermont", 0, "CC", phase="existing", first_use=False)[1] == (Decimal("0"),) * 2
    assert estimate("vermont", 0, "CC", phase="existing", exemption="no_court_fee_case")[1] == (Decimal("0"),) * 2
