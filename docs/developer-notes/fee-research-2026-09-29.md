# E-filing service and convenience fee research

Researched September 29, 2026. These are separate from the court filing fees.

## Published rules

| State | eCheck/ACH processing | Credit card processing | Platform fee |
| --- | --- | --- | --- |
| Massachusetts | $0.25 per submission | 2.89% of court fee plus Tyler fee | $22 when initiating a new case; not subsequent filings |
| Vermont | $1.00 | 2.89% | $14 per filer or firm per case, on their first filing; exemptions apply |

Sources:

- [Massachusetts Trial Court e-filing guidance](https://www.mass.gov/info-details/learn-about-efiling-in-the-trial-court)
- [Massachusetts Superior Court guidance](https://www.mass.gov/info-details/efiling-in-the-superior-court)
- [Vermont Judiciary e-filing fees and exemptions](https://www.vtcourts.gov/about-vermont-judiciary/electronic-access/electronic-filing)
- [Illinois official e-filing FAQ](https://efile.illinoiscourts.gov/faq-page/) confirms separate processing fees, without publishing rates on that page.
- [Illinois Supreme Court Commission on Access to Justice guide, hosted by Winnebago County](https://www.cc.co.winnebago.il.us/assets/1/7/Step_5_efile_guide.pdf) lists 2.89% for credit cards. The Illinois bank fee below was verified by test quote.

Vermont's $14 fee is not simply a new-case fee: a different filer or firm can owe it on an existing case. Its guidance says no-court-fee cases are exempt and specifically instructs protection-order filers to select a waiver payment account. That statutory exemption is distinct from an income-based waiver.

## Authenticated test quotes

Used the documented test EFSP endpoint and state-specific credentials in `efile_app/.env`. Requested only authentication, read-only account/code lookups, and `POST /jurisdictions/{state}/filingreview/courts/{court}/filing/fees`. Used synthetic parties and the public `testing/sample_test.pdf`. No filings were submitted, payment accounts created, or payments initiated.

| Court and new case | Existing account type | Court fee | Service fee | Convenience fee | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| Illinois, Calhoun: Civil No Contact Order | Bank account | $0 | $0 | $0 | $0 |
| Illinois, Calhoun: residential eviction | Bank account | $256 | $0 | $0.25 | $256.25 |
| Illinois, Calhoun: either case above | Waiver | $0 | $0 | $0 | $0 |
| Vermont, Chittenden: Relief from Abuse | Visa | $0 | $14 | $0.40 | $14.40 |
| Vermont, Chittenden: contested dissolution with minor children | Visa | $295 | $14 | $8.93 | $317.93 |

The Vermont paid quote matches `(295 + 14) * 2.89% = 8.93`, rounded to cents. The protection-order quote shows that a zero case-code fee does not imply a zero envelope total with an ordinary payment account. The documented exemption requires a waiver payment account; this test account did not have one, so that path was not quoted.

The Illinois credit card was expired and returned HTTP 422. There was no Vermont bank account. Massachusetts authentication succeeded, but the account had only a waiver payment account, so ordinary processing fees could not be tested. Lowell initial-case quotes were rejected by the proxy because that test court does not allow initial filings. A further Suffolk Probate adult name-change attempt could not construct a complete payload from the returned code lists; no quote was sent for that attempt.

Early requests also hit expected payload validation: `vermont:sc` is a parent location, not a valid initial filing destination; Illinois firm accounts cannot identify the filer as the party; the Vermont divorce case requires a minor party. Correcting these produced the successful quotes above.

[Sanitized response evidence](fixtures/fee-quotes-2026-09-29.json) retains code IDs, amounts and errors, but no credentials, authentication tokens, or payment account IDs. These staging samples establish observed behavior, not universal production rules.

## Implications for estimates

- Do not apply the current Illinois flat $0.25 setting to every filing. The tested free bank-account filing had no convenience charge, while the paid filing did. Credit cards have a percentage charge.
- Model processing charges by state and payment method, separately from platform fees. Before a method is known, display an estimate or range with that uncertainty.
- Vermont also needs first-filing-per-filer/firm context and statutory exemptions. Do not treat every statutory exemption as a claim of low income or create an account without the user's choice.
- Case and filing code fees are base court charges. These samples do not encode all service/processing charges; the quote response returns them as separate `allowanceCharge` entries.
- A base court fee of $0 must not trigger a promise of no charge. That promise should use a current successful quote for the selected payment account and complete fee inputs.
- Keep the existing safeguards for amount in controversy, civil claim amount and estate amount. This research did not test those variable-amount scenarios and does not establish that a preliminary zero is final.

Follow-up implementation: state `fee_estimates.surcharges` now separates payment-method processing rules, platform timing and exemptions. The unconditional Illinois setting has been replaced. Estimates preserve unknown payment methods and prior per-filer payment as ranges; live quotes remain authoritative.
