# Vermont statutory fee estimate validation

Issue: [#265](https://github.com/SuffolkLITLab/LITEFile/issues/265). Catalog and browser checks performed October 14, 2026 against the test proxy and locally rendered Django views.

## What changed

Paid Vermont accounts now retain the $14 first-filing service fee when court fees are zero. Estimates include card or bank processing costs and retain uncertainty for an existing case when prior payment by this filer is unknown. The unused zero-court-fee shortcut was removed. Unknown/amount-dependent fees remain unknown; selecting WV does not turn an estimate into a confirmed quote.

Narrow case-label rules suggest a managed waiver account for voter-checklist petitions and new abusive-litigation cases. The payment page shows the suggestion before selection, explains that income-based documents are unnecessary for the exemption, and warns that paid accounts may incur service/processing charges. Setup remains an explicit filer choice. Payment and Review distinguish a claimed statutory exemption from a financial-hardship waiver request.

## Actual code exploration

Read the test proxy's case types for Chittenden (`sc:chittendon`), categories Civil (`7`), Probate or Mental Health (`169`), and Family (`210`), with `timing=Initial`. Then fetched `filing_types/?initial=true&category_id=…&type_id=…` and selected the exact `Initial Filing` label. Party types were also inspected for the initial five examples. Sanitized rows are in [the regression fixture](../../efile_app/efile/tests/fixtures/vermont_statutory_fee_codes.json). These are code-table responses, not fee quotes.

| Case label | Category | Case code | Initial filing code | Entry fee |
| --- | --- | --- | --- | ---: |
| Add Name to Voter Checklist | 7 | 6055 | 9563 | $0 |
| Permission to File Pursuant to 15 VSA Sec 1185 | 7 / 169 / 210 | 14000 / 14001 / 13999 | 9563 / 9568 / 9564 | $0 |
| Restricting Abusive Litigation Pursuant to 15 VSA Sec 1182 | 7 / 169 / 210 | 14360 / 14362 / 14361 | 9563 / 9568 / 9564 | $0 |
| Relief from Abuse | 210 | 6177 | 9564 | $0 |
| Appeal - Administrative Agency (negative control) | 7 | 6063 | 9563 | $295 |

The live catalog included the newer 14360/14361/14362 labels absent from the checked-in benchmark snapshot. The snapshot also contains zero-price conversion cases; the live initial catalog filters several out. Neither a historical nor a current zero alone establishes statutory eligibility. Generic administrative appeals, probate placeholders and conversion labels do not get the new exemption suggestion.

## Sources and eligibility limits

- [17 V.S.A. § 2148](https://legislature.vermont.gov/statutes/section/17/043/02148) establishes the voter-checklist court-fee exemption. Using WV follows the [Civil Division guide](https://www.vtcourts.gov/media/12012), pp. 10–11, general guidance for statutorily exempt filers. The specific voter-checklist WV behavior still needs a fresh authenticated test quote/court confirmation; the Judiciary's short list of named WV exemptions does not explicitly list this case.
- The same guide, p. 7, expressly permits a waiver account for the **Permission to File Pursuant to 15 VSA Sec 1185** label. This mapping relies on that court instruction, not an inference that restricted parties qualify under § 1182(e). The guide describes this heading as a petition to restrict litigation, while the statute distinguishes permission by a restricted party; partner clarification of that label remains useful.
- [15 V.S.A. § 1182(c), (e)](https://legislature.vermont.gov/statutes/section/15/021/01182) covers a new petition and exempts the unrestricted party. Automatic matching is limited to new cases. An existing-case label does not establish which side is filing; later motions need filing/party-specific eligibility work before extending this suggestion.
- [Vermont Judiciary e-filing guidance](https://www.vtcourts.gov/about-vermont-judiciary/electronic-access/electronic-filing) supports the existing protection-order rules and distinguishes automatic criminal exemptions from exemptions claimed through WV.

No broad “statutory administrative review” pattern was added. The observed generic administrative appeal is paid; court-records appeals and other zero-price case types need their own verified eligibility mappings.

## Before and after examples

These are **estimates calculated from the fetched code rows**, one Initial Filing document and no optional services. Fresh authenticated quotes were blocked: both a direct test login and the application's configured authentication helper returned HTTP 403. No submissions, payments or account creation occurred.

| Example | Old paid estimate | New card estimate | New bank estimate | Before choosing a method |
| --- | ---: | ---: | ---: | ---: |
| Voter checklist 6055 | ~$0.00 | ~$14.40 | ~$15.00 | $14.40–$15.00 |
| Permission to file 14000/14001/13999 | ~$0.00 | ~$14.40 | ~$15.00 | $14.40–$15.00 |
| Restricting abusive litigation 14360/14362/14361 | ~$0.00 | ~$14.40 | ~$15.00 | $14.40–$15.00 |
| Relief from Abuse 6177 | Already ~$14.40 card / ~$15.00 bank | ~$14.40 | ~$15.00 | $14.40–$15.00 |
| Administrative appeal 6063 | Already included service fees | ~$317.93 | ~$310.00 | $310.00–$317.93 |

Card calculation: `$14 + round($14 × 2.89%, 2) = $14.40`. Bank calculation: `$14 + $1 = $15`. The [recorded September 29 Tyler quote](fixtures/fee-quotes-2026-09-29.json) for RFA 6177/9564 with CC confirms $14.40, and the paid dissolution example confirms $317.93. Those are historical observations, not fresh quotes for the newly mapped codes. Illinois $0 and Massachusetts $22.64 card/$22.25 bank cases remain covered by regression tests.

After explicit WV selection the existing flow says $0 due now and preserves court review; it does not fetch or fabricate a live quote. A saved WV account does not automatically claim an exemption on a later visit.

## Validation and screenshots

[Desktop and mobile screenshot gist](https://gist.github.com/nonprofittechy/060bb60ba5bc1b23234b13714c8c934a) contains nine screenshots: four case examples before/after selection and a 390-pixel mobile view. The gist explains the synthetic drafts and mocked account endpoints. Screenshots were captured under `/tmp`, not committed to this repository.

Browser checks use the actual Django payment view, real sanitized code fixtures, and production JavaScript with synthetic account responses. Assertions cover the estimate, visible suggestion, absent income upload, one setup request only after selection, exemption-specific confirmation, enabled Review, no uncaught browser errors, and no mobile horizontal overflow. They do not establish live WV pricing.

Results: the six-file Python regression run passed **301 tests**. After removing the unused surcharge branch and adding two explicit Massachusetts zero-court-fee checks, the surcharge suite was rerun separately. The JavaScript checks passed **17 tests**. Ruff, ty, template formatting and changed-file ESLint checks passed.

Commands run from `efile_app/`:

```bash
uv run pytest -q efile/tests/test_fee_surcharges.py efile/tests/test_fee_estimates.py efile/tests/test_managed_waiver.py efile/tests/test_fee_quotes.py efile/tests/test_waiver_documents.py efile/tests/test_review_submit_flow.py
node --test js-tests/payment.test.js js-tests/review-payment.test.js
uv run ruff check .
uv run ty check
uv run djlint efile/templates/efile/payment.html efile/templates/efile/review.html --check
npx eslint efile/static/js/payment.js js-tests/payment.test.js
```

## Claude review

Claude reviewed the diff and relevant code, ran the affected tests, and independently read the official sources. Verified and implemented suggestions: separate 1182/1185 source mappings and explain their limits; use a source-neutral link label; show the exemption note once; distinguish exemption confirmations on Payment and Review; add real-estimator screen/negative tests and cross-division fixtures; update configuration documentation and remove the unused zero-fee shortcut.

Existing-case 1182 motion support remains out of automatic matching because eligibility needs more than the case name. A requested follow-up Claude review could not authenticate because its OAuth token had expired. The initial review completed; the changes responding to it were validated locally.
