# Court bank payment restrictions

The Fees account list, saving a payment selection, fee quotes, and final submission
respect the selected court's `restrictbankaccountpayment` location setting from
`/jurisdictions/{jurisdiction}/codes/courts/{court}/codes`. The proxy's
`CodesService.getCourtLocationCodes` returns a location object with that field;
`CourtLocationInfo` declares it as a string.

Only boolean false or the string `False` (case and surrounding whitespace ignored)
permits `BankAccount`. True restricts it; absent, malformed, or unavailable settings
leave bank payments unavailable until a successful retry. Cards and waivers do not
need the bank setting. Account lists without a current draft remain account-wide;
lists for a draft filter bank accounts and explain the restriction. A list with no
bank accounts does not perform the extra location lookup. Adding an account still
uses TOGA; the account actually returned by TOGA is checked regardless of the setup
button's label or requested account type.

Each save, quote, and submission checks current policy. Quotes and submission also
resolve the actual account type from the authenticated active account list, then
send the checked payment ID instead of trusting the browser payload. Final
submission checks that fee-affecting draft fields did not change during the account
lookup before claiming the draft. A policy or account failure leaves the draft
editable and returns a link to Fees. Review does not automatically retry fees for
this kind of error.

## Validation

`efile/tests/test_court_payments.py` covers boolean/string flags across Illinois,
Massachusetts, and Vermont, malformed and missing metadata, lookup failures,
filtered choices, stale and forged requests, concurrent court changes, and recovery
through a card. External HTTP responses are synthetic.

Run the opt-in Chromium flows from `efile_app/`:

```bash
COURT_PAYMENT_BROWSER_TESTS=1 \
COURT_PAYMENT_EVIDENCE_DIR=/tmp/litefile-298-evidence \
uv run pytest -q efile/tests/test_court_payments.py
```

The browser drives real Fees, Review, and submission endpoints, covering a
restricted court, an outage with keyboard retry, a restriction introduced after a
bank quote, and a restriction introduced after saving payment. It checks mobile
width and runs axe on the payment form. Court and storage services are synthetic;
these tests do not make live filings or payments. Screenshots belong in a linked
gist, not this repository.
