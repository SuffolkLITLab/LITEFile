# Filing-code direct test inventory

Checked 2026-10-13. This note lists filing queries and form aliases that automated tests actually assert, then separately records read-only provider-catalog path audits. Test fixtures and source inventories are not equivalent to executing every guided interview and submitting its rendered PDFs. In particular, `test_guided_form_surfaces.py` controls PDF text through mocks; it does not open the actual generated PDFs.

## Automated filing-search assertions

The relevant search assertions are in [`test_filing_code_search.py`](../../efile_app/efile/tests/test_filing_code_search.py), [`test_guided_form_aliases.py`](../../efile_app/efile/tests/test_guided_form_aliases.py), and [`test_guided_form_surfaces.py`](../../efile_app/efile/tests/test_guided_form_surfaces.py). Except where called a captured provider replay below, these run against small synthetic catalogs/indexes. They validate behavior and constraints, not current court availability.

| Test assertion | Query / printed ID | Expected result | Stage and path constraints | Test data |
|---|---|---|---|---|
| Generic synonym search (parameterized for IL, MA, VT) | `eviction`, `evicted`, `unlawful detainer`, `summary process`, `forcible entry and detainer` | Two synthetic eviction paths | Both synthetic courts; context/facets tested | Synthetic |
| Generic district search | `district civil eviction complaint` | Synthetic `Summary Process Complaint` | District / Civil / Summary Process | Synthetic |
| Generic debt exclusion | `debt eviction` | No result | N/A | Synthetic |
| Typo, stage, ranking | `motions to dismiss`, `complants`, `eviciton`, `unlawfull detainer`, `notice`, `eviction` | Subsequent dismiss motions; typo corrections; `notice` has none; subsequent eviction returns four paths | Synthetic stage counts: `notice` subsequent 0; `eviction` subsequent 4 | Synthetic |
| Initial complaint language (legacy and bulk transports) | `complaint`, `file a complaint`, `small claims complaint`, `divorce complaint`, `end marriage`, `relief from abuse complaint`, `RFA`, `start relief from abuse case` | Vermont synthetic `Initial Filing` paths | Initial only; RFA, Small Claims, and Divorce types constrained; subsequent excludes these initial filings | Synthetic |
| Illinois eviction sealing | `seal eviction`, `seal my eviction`, `eviction record sealing`, `hide eviction case`, `remove eviction from public record` | Exact `Motion to Remove Eviction Court File from Public Record` | Subsequent, DuPage, Residential - Eviction; excludes Criminal and initial filing | Synthetic DuPage catalog using the exact observed title/code family; not a live request |
| Seal vocabulary candidates | `seal eviction` with `Impound/Seal`, `Filed Under Seal`, and `Motion for Redaction & Confidential Filing` | Candidate matches retained; unrelated `Other Document Not Listed (Confidential)` excluded | Language/token regression, not a confirmed Illinois path | Synthetic |
| Captured Vermont initial paths | `relief from abuse complaint`, `RFA`, `small claims complaint` | Code `9564` `Initial Filing` for RFA (3 case types); code `9563` `Initial Filing` for Small Claims (8 case types) | Each query scoped across 14 audited county Superior Court units; replayed capture, not runtime live calls | Dated provider capture; details below |
| Printed form identifiers, Illinois | `ATJ 251.5`, `ATJ 108.4` | Exact `Financial Affidavit` / `Financial Affidavit Filed` candidates; exact `Parenting Plan` candidate | Test uses subsequent mock Find-code paths, Family / Divorce or Parenting Responsibilities | Mocked path catalog; real current registry scan |
| Printed form identifiers, Vermont | `400-00813B`, `100-00127` | Exact `813B Financial Affidavit`; exact `Small Claims - Financial Disclosure Affidavit` | Subsequent mock paths, Family / Divorce or Civil / Small Claims $1,000 or less | Mocked path catalog; real current registry scan |

The form-surface test also asserts jurisdiction isolation: an Illinois lookup does not resolve Vermont IDs and vice versa. Keyword extraction uses controlled text and disables model extraction. For `ATJ 251.5`, two exact filing labels remain advisory/ambiguous and the extractor makes no filing-type guess. The additional [`test_exact_provider_filing_label.py`](../../efile_app/efile/tests/test_exact_provider_filing_label.py) regression checks two Vermont synthetic-index collisions: exact `Application to Waive Filing and Service Fees` still finds Civil and Probate labels outside a form-ID alias's Civil-only scope, while ID `600-00228` returns only its Civil-scoped path; exact `Small Claims Answer` finds both that exact label and `Answer`, while ID `100-00126` returns only `Answer` and remains subsequent. It also compares grouped label counts with labels rebuilt from paths. These are synthetic route tests, not live availability checks.

The [`form search relevance benchmark`](form-search-relevance-benchmark-2026-10-13.md) replays 22 queries (16 Vermont, 6 Illinois) against frozen synthetic court/category/type paths with captured provider labels. The Vermont exact fee-waiver label control is run at both initial and subsequent stages across Civil, Family, and Probate, including Probate as a negative scope check for the form-ID alias. The benchmark exercises the actual `search_paths` implementation, but does not assert live case eligibility; per-query results and limitations are recorded in the linked benchmark report and fixtures.

The other search regressions in `test_filing_code_search.py` exercise generic action semantics (complaints, answers, motions, stipulations, orders, notices, proof of service, and fee waivers), grouping, ranking, filters, pagination, and index lifecycle. They use synthetic paths and should not be read as state-specific filing availability tests.

## Form-alias assertions

`test_guided_form_aliases.py` tests these Vermont ID-to-path restrictions directly. The positive assertions use subsequent paths except where noted; this describes the tested paths, not every configured stage:

| Printed form ID | Query alias / expected exact catalog label | Stage and case scope | Negative assertion |
|---|---|---|---|
| `400-00151` (legacy `400-00151N` is also inventoried) | “Affidavit in Support of Relief from Abuse Complaint” → `Affidavit` | Initial Family / Relief from Abuse | Not minor RFA, Small Claims, Divorce; bare “affidavit” does not trigger |
| `400-00151M` | Child-specific affidavit title → `Affidavit` | Subsequent path alias in this test (the source audit associates the form with initial filing) / Family / Relief from Abuse on Behalf of a Minor | Not adult RFA |
| `100-00127` | ID → `Small Claims - Financial Disclosure Affidavit` | Subsequent Civil / small-claims case types | Not initial, Family, or generic “financial affidavit” |
| `400-00831` | ID → `Notice of Pro Se Appearance` | Subsequent Family / Divorce | Not initial; generic “notice of appearance” does not trigger the ID alias |
| `100-00265` | ID → `Notice of Pro Se Appearance` | Subsequent Civil / Collection - Non-Credit Card | Not Certificate of Service or initial |
| Shared title concept “Notice of Appearance for Self-Represented Party” | Title → `Notice of Pro Se Appearance` | Subsequent Civil / Collection - Non-Credit Card and Family / Divorce | Title association only; the numeric ID path is Civil-scoped |
| `100-00126` | ID → `Answer` | Subsequent Civil / small-claims case types | Not initial or credit-card collection |

`test_every_illinois_generated_alias_has_source_and_registry_parity` is a dynamic parity regression: it iterates every Illinois alias rule in [`guided_form_search_aliases.json`](../../efile_app/efile/data/guided_form_search_aliases.json), requires an inventory output with a matching printed form ID, confirms registry label parity, indexes the alias on the configured label/stage/category/court scope, and asserts it does not leak to a different filing label (or a different provider court where scoped). This is 57 Illinois path-alias rules spanning 26 printed form IDs/concepts; the regression runs over all 57 rules. It does not execute each interview or prove each court path is eligible. The compact table below enumerates every ID and the filing label(s)/stage covered by those rule assertions; unscoped is not a claim of universal availability. See the complete rule-by-rule table below and [`guided_interview_inventory.json`](../../efile_app/efile/data/guided_interview_inventory.json) with its referenced manifests.


| Printed ID | Expected filing label(s) in alias rule(s) | Stage(s) asserted | Rule scope |
|---|---|---|---|
| `ATJ 108.4` | Parenting Plan | Subsequent | Family |
| `ATJ 111.5` | Appearance | Subsequent | Family |
| `ATJ 128.4` | Support Information Sheet | Initial; subsequent | Family |
| `ATJ 134.4` | Additional Parenting Time | Subsequent | Family |
| `ATJ 1405.2` | Affirmative Defenses | Subsequent | Civil |
| `ATJ 251.5` | Financial Affidavit; Financial Affidavit Filed | Subsequent | Family; second label Cook DR court codes only |
| `ATJ 254.3` | Additional Health Insurance | Subsequent | Family |
| `ATJ 255.3` | Additional My Debts | Subsequent | Family |
| `ATJ 256.3` | Additional Cash and Cash Equivalents | Subsequent | Family |
| `ATJ 260.3` | Additional Motor Vehicles | Subsequent | Family |
| `ATJ 261.3` | Additional Lawsuits and Claims | Subsequent | Family |
| `ATJ 405.4` | Order of Protection | Initial | Family / Order of Protection |
| `ATJ 503.11` | Appearance; Appearance Filed; Appearance Filed - Fee; Appearance Filed - Fee Waived; Appearance Filed - Fee Waiver; Appearance Filed - No Fee; Appearance Filed - No Fee Paid | Subsequent | Civil; provider-coded Cook subsets for six exact provider variants |
| `ATJ 504.4` | Jury Demand/Request; Jury Demand Filed - Fee; Jury Demand Filed - No Fee | Subsequent | Civil; provider-coded Cook subsets for two exact provider variants |
| `ATJ 520.5` | Certificate of Exemption from eFiling | Initial | No category restriction in rule |
| `ATJ 601.9` | Application Waiver of Court Fees (Civil) | Subsequent | Civil |
| `ATJ 602.8` | Order for Waiver of Fees/Assessments | Subsequent | Civil |
| `ATJ 851.7` | Proof of Delivery | Initial; subsequent | Civil, Eviction, Family (by source output) |
| `AP-P 503.5` | Appearance | Subsequent | No category restriction in rule; source output is the e-file appearance PDF |
| `DV-B 126.2` | Additional Investment/Brokerage Accounts, Mutual Funds, and Secured or Unsecured Notes | Subsequent | Family |
| `DV-C 124.2` | Additional Cash and Prepaid Debit Card | Subsequent | Family |
| `DV-CF 123.2` | Additional Certificates of Deposit | Subsequent | Family |
| `DV-RE 127.2` | Additional Real Estate | Subsequent | Family |
| `DV-V 133.2` | Additional Valuable Collectibles | Subsequent | Family |
| `EXC-M 4702.2` | Motion to Vacate & Expunge Eligible Cannabis Convictions | Subsequent | No category restriction in rule |
| `PD-ASL 805.3` | Proof of Delivery | Subsequent | Civil, Eviction, Mortgage Foreclosure (by source output) |

For the full per-rule court code lists, source URLs, evidence status, source output IDs, and the individual 57 rows, see [`guided_form_search_aliases.json`](../../efile_app/efile/data/guided_form_search_aliases.json). The dynamic test checks each row and the label’s crosswalk presence; it does not query each court against the live provider.


#### Illinois alias rules asserted by the dynamic test

Each row is one alias rule iterated by the parity test. “Any/unscoped” describes absence of that constraint in the rule, not an inference that every court offers it. Court codes are shown exactly where a rule scopes them.

| Printed ID | Source output | Exact filing label | Stage | Category and case-type scope | Court-code scope |
|---|---|---|---|---|---|
| `ATJ 851.7` | `Appearance:x.additional_proof` | Proof of Delivery | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 851.7` | `AppearanceEfile:x.additional_proof` | Proof of Delivery | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 128.4` | `ChildSupportModification:support_information_sheet` | Support Information Sheet | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `ChildSupportModification:x.additional_proof` | Proof of Delivery | subsequent | Family; any/unscoped | any/unscoped |
| `PD-ASL 805.3` | `DelayAForeclosureSale:x.additional_proof` | Proof of Delivery | subsequent | Civil, Mortgage Foreclosure; any/unscoped | any/unscoped |
| `ATJ 111.5` | `Divorce:divorce_appearance` | Appearance | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 128.4` | `Divorce:support_information_sheet` | Support Information Sheet | initial | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `EmergencyMotionClaimExemption:additional_proof` | Proof of Delivery | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 851.7` | `ExtendTimeOfEviction:x.additional_proof` | Proof of Delivery | subsequent | Civil, Eviction; any/unscoped | any/unscoped |
| `ATJ 256.3` | `FinancialAffidavit:additional_cash` | Additional Cash and Cash Equivalents | subsequent | Family; any/unscoped | any/unscoped |
| `DV-CF 123.2` | `FinancialAffidavit:additional_cd` | Additional Certificates of Deposit | subsequent | Family; any/unscoped | any/unscoped |
| `DV-V 133.2` | `FinancialAffidavit:additional_collectibles` | Additional Valuable Collectibles | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 255.3` | `FinancialAffidavit:additional_debts` | Additional My Debts | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 261.3` | `FinancialAffidavit:additional_lawsuits` | Additional Lawsuits and Claims | subsequent | Family; any/unscoped | any/unscoped |
| `DV-C 124.2` | `FinancialAffidavit:additional_money` | Additional Cash and Prepaid Debit Card | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 260.3` | `FinancialAffidavit:additional_motor_vehicle` | Additional Motor Vehicles | subsequent | Family; any/unscoped | any/unscoped |
| `DV-B 126.2` | `FinancialAffidavit:additional_other_investments` | Additional Investment/Brokerage Accounts, Mutual Funds, and Secured or Unsecured Notes | subsequent | Family; any/unscoped | any/unscoped |
| `DV-RE 127.2` | `FinancialAffidavit:additional_real_estate` | Additional Real Estate | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 251.5` | `FinancialAffidavit:fa_primary` | Financial Affidavit | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 254.3` | `FinancialAffidavit:insurance` | Additional Health Insurance | subsequent | Family; any/unscoped | any/unscoped |
| `AP-P 503.5` | `ILAOAppearance:illinois_appearance_attachment` | Appearance | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 851.7` | `Motion:x.additional_proof` | Proof of Delivery | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 851.7` | `MotionProcessServer:x.additional_proof` | Proof of Delivery | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 405.4` | `OrderOfProtection:plenary_op` | Order of Protection | initial | Family, Order of Protection; any/unscoped | any/unscoped |
| `ATJ 134.4` | `ParentingPlan:additional_parenting_time` | Additional Parenting Time | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 108.4` | `ParentingPlan:parenting_plan` | Parenting Plan | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `ParentingTimeSchedule:proof_of_delivery` | Proof of Delivery | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `ParentingTimeSchedule:x.additional_proof` | Proof of Delivery | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `PetitionForRuleToShowCauseFamily:proof_of_delivery` | Proof of Delivery | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `PetitionForRuleToShowCauseFamily:proof_of_delivery_lawyer` | Proof of Delivery | subsequent | Family; any/unscoped | any/unscoped |
| `ATJ 851.7` | `ProofOfDelivery:proof_of_delivery` | Proof of Delivery | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 851.7` | `ProofOfDelivery:x.additional_proof` | Proof of Delivery | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `PD-ASL 805.3` | `RemoveEvictionFromPublicRecord:x.additional_proof` | Proof of Delivery | subsequent | Civil, Eviction; any/unscoped | any/unscoped |
| `ATJ 1405.2` | `RespondToALawsuit:affirmative_defenses` | Affirmative Defenses | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 851.7` | `RespondToALawsuit:x.additional_proof` | Proof of Delivery | subsequent | Civil; any/unscoped | any/unscoped |
| `PD-ASL 805.3` | `RespondToAnEviction:x.additional_proof` | Proof of Delivery | subsequent | Civil, Eviction; any/unscoped | any/unscoped |
| `PD-ASL 805.3` | `RespondToAnEviction:x.answer_additional_proof` | Proof of Delivery | subsequent | Civil, Eviction; any/unscoped | any/unscoped |
| `PD-ASL 805.3` | `RespondToForeclosureComplaint:x.additional_proof` | Proof of Delivery | subsequent | Civil, Mortgage Foreclosure; any/unscoped | any/unscoped |
| `ATJ 851.7` | `SmallClaimsComplaint:x.additional_proof` | Proof of Delivery | subsequent | Civil; any/unscoped | any/unscoped |
| `PD-ASL 805.3` | `VacateDefaultForeclosure:x.additional_proof` | Proof of Delivery | subsequent | Civil, Mortgage Foreclosure; any/unscoped | any/unscoped |
| `ATJ 851.7` | `VacateDefaultJudgment:x.additional_proof` | Proof of Delivery | subsequent | Civil; any/unscoped | any/unscoped |
| `EXC-M 4702.2` | `il-cannabisexpungement-cxp-motion-to-vacate-and-expunge-cannabis-expungement` | Motion to Vacate & Expunge Eligible Cannabis Convictions | subsequent | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 851.7` | `il-minorguardianshipdischarge-aoic-proof-of-delivery-minor-guardianship-discharge` | Proof of Delivery | initial | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 503.11` | `—` | Appearance | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 504.4` | `—` | Jury Demand/Request | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 520.5` | `—` | Certificate of Exemption from eFiling | initial | any/unscoped; any/unscoped | any/unscoped |
| `ATJ 601.9` | `—` | Application Waiver of Court Fees (Civil) | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 602.8` | `—` | Order for Waiver of Fees/Assessments | subsequent | Civil; any/unscoped | any/unscoped |
| `ATJ 503.11` | `—` | Appearance Filed | subsequent | any/unscoped; any/unscoped | cook:cvd2, cook:cvd3, cook:cvd4, cook:cvd5, cook:cvd6, cook:dr1, cook:dr2, cook:dr3, cook:dr4, cook:dr5, cook:dr6 |
| `ATJ 503.11` | `—` | Appearance Filed - Fee | subsequent | any/unscoped; any/unscoped | cook:chd1, cook:cvd1, cook:cvd2, cook:cvd3, cook:cvd4, cook:cvd5, cook:cvd6, cook:dr1, cook:dr2, cook:dr3, cook:dr4, cook:dr5, cook:dr6, cook:eld1, cook:eld2, cook:eld3, cook:eld4, cook:eld5, cook:eld6, cook:law1, cook:law2, cook:law3, cook:law4, cook:law5, cook:law6 |
| `ATJ 503.11` | `—` | Appearance Filed - No Fee | subsequent | any/unscoped; any/unscoped | cook:chd1, cook:dr1, cook:dr2, cook:dr3, cook:dr4, cook:dr5, cook:dr6, cook:law1, cook:law2, cook:law3, cook:law4, cook:law5, cook:law6 |
| `ATJ 503.11` | `—` | Appearance Filed - Fee Waiver | subsequent | any/unscoped; any/unscoped | cook:chd1 |
| `ATJ 503.11` | `—` | Appearance Filed - Fee Waived | subsequent | any/unscoped; any/unscoped | cook:eld1, cook:eld2, cook:eld3, cook:eld4, cook:eld5, cook:eld6, cook:law1, cook:law2, cook:law3, cook:law4, cook:law5, cook:law6 |
| `ATJ 503.11` | `—` | Appearance Filed - No Fee Paid | subsequent | any/unscoped; any/unscoped | cook:eld1, cook:eld2, cook:eld3, cook:eld4, cook:eld5, cook:eld6 |
| `ATJ 504.4` | `—` | Jury Demand Filed - Fee | subsequent | any/unscoped; any/unscoped | cook:cvd1, cook:cvd2, cook:cvd3, cook:cvd4, cook:cvd5, cook:cvd6 |
| `ATJ 504.4` | `—` | Jury Demand Filed - No Fee | subsequent | any/unscoped; any/unscoped | cook:cvd1, cook:cvd2, cook:cvd3, cook:cvd4, cook:cvd5, cook:cvd6, cook:law1, cook:law2, cook:law3, cook:law4, cook:law5, cook:law6 |
| `ATJ 251.5` | `—` | Financial Affidavit Filed | subsequent | any/unscoped; any/unscoped | cook:dr1, cook:dr2, cook:dr3, cook:dr4, cook:dr5, cook:dr6 |

## Read-only provider-catalog path observations

These are observations from dated API reads or persisted response captures, separate from automated synthetic tests. They establish that labels/paths appeared in the queried environment and scope only. They do not prove a filer is eligible, that a path remains available today, or that every court has the same configuration.

### Illinois selected-label path audit

The [`Illinois path audit fixture`](fixtures/illinois-guided-form-path-audit-2026-10-13.json) records read-only responses from `efile-test.suffolklitlab.org`, checked 2026-10-13. It checked `Appearance`, `Financial Affidavit`, `Parenting Plan`, and `Support Information Sheet`, at initial and subsequent stages, for DuPage `dupage`, Cook Domestic Relations `cook:dr`, and Lake `lake`. In the captured scope:

| Court | Stage | Observed exact labels and counts | Scope note |
|---|---|---|---|
| DuPage | Initial | None of the four labels | Family category checked |
| DuPage | Subsequent | `Appearance`: 63 paths | Two Family category IDs checked; sample case type Change of Venue - Family |
| Cook DR | Initial / subsequent | No matching paths for the four labels | All observed categories beginning `Domestic Relations` checked |
| Lake | Initial | None of the four labels | Family category checked |
| Lake | Subsequent | Each of the four labels: 78 paths | Family categories checked; exact case-type IDs are in fixture |

### Illinois Cook exact-label audit

The [`Cook label audit fixture`](fixtures/illinois-cook-guided-form-label-audit-2026-10-13.json) contains nine reviewed label/stage/court-code records. All are subsequent. The titles and labels are exact provider wording; the code arrays in the fixture are the authoritative list of observed routes:

| Source form title | Exact provider filing label | Court-code scope |
|---|---|---|
| `APPEARANCE (CIVIL)` | `Appearance Filed` | `cook:cvd2`–`cvd6`, `cook:dr1`–`dr6` |
| `APPEARANCE (CIVIL)` | `Appearance Filed - Fee` | `cook:chd1`, `cook:cvd1`–`cvd6`, `cook:dr1`–`dr6`, `cook:eld1`–`eld6`, `cook:law1`–`law6` |
| `APPEARANCE (CIVIL)` | `Appearance Filed - No Fee` | `cook:chd1`, `cook:dr1`–`dr6`, `cook:law1`–`law6` |
| `APPEARANCE (CIVIL)` | `Appearance Filed - Fee Waiver` | `cook:chd1` |
| `APPEARANCE (CIVIL)` | `Appearance Filed - Fee Waived` | `cook:eld1`–`eld6`, `cook:law1`–`law6` |
| `APPEARANCE (CIVIL)` | `Appearance Filed - No Fee Paid` | `cook:eld1`–`eld6` |
| `JURY REQUEST (CIVIL)` | `Jury Demand Filed - Fee` | `cook:cvd1`–`cvd6` |
| `JURY REQUEST (CIVIL)` | `Jury Demand Filed - No Fee` | `cook:cvd1`–`cvd6`, `cook:law1`–`law6` |
| `FINANCIAL AFFIDAVIT` | `Financial Affidavit Filed` | `cook:dr1`–`dr6` |

These observations are deliberately court-scoped; the same source document does not imply a universal statewide filing label.

### Illinois eviction record-removal search miss

The [`eviction record-removal audit`](fixtures/illinois-eviction-record-removal-audit-2026-10-13.json) is a direct read-only catalog scan dated 2026-10-13. It checked subsequent option lists for 360 Illinois court codes (all requests succeeded): 784,189 option rows total; exact-title count for `Motion to Remove Eviction Court File from Public Record` was zero in those current responses. A targeted scan found 855 case-type rows matching the audit's eviction-related discovery terms, again with zero exact target-title rows. This is a documented miss, not evidence that no alternative filing procedure exists.

A historical repository snapshot, [`Illinois Tyler catalog snapshot`](../../benchmarking/promptfoo/data/tyler_catalog/illinois/catalog.json), contains that exact DuPage subsequent label with codes `309683`, `309736`, `309746`, and `309756`, but blank category/type metadata. The snapshot is dated 2026-08-23 in its source metadata. It is not a current live availability or eligibility confirmation.

### Vermont captured initial paths

The [`Vermont initial-path audit`](fixtures/vermont-initial-filing-audit-2026-10-13.json) records a read-only provider capture on 2026-10-13. Fourteen county Superior Court units had all three RFA paths, each with exact `Initial Filing` code `9564`, and all eight audited Small Claims case types with exact `Initial Filing` code `9563`. Three enabled selector courts had no initial Family category (`vermont:ed`, `vermont:jb`, `vermont:supreme`). The fixture lists the exact case-type names and IDs, per-court responses, and request errors (zero). Tests replay this fixture; they do not fetch the provider at test time.

The [`Vermont supporting-form label audit`](fixtures/vermont-supporting-form-labels-2026-10-13.json) contains 20 reviewed source-document associations (including one unmapped vital-records group). It records labels and observed category/case-type evidence; several records do not have a complete case-type restriction. The specifically asserted path aliases are the six Vermont IDs in the preceding section. The rest of the fixture is reviewed catalog/source evidence, not individual automated path-query tests. The complete 20-record title/label inventory is below; `—` means no exact filing label was established. Stage is from the source association; it is distinct from the specifically asserted aliases above.

| Printed ID(s) | Source document title | Exact observed filing label | Source stage/category/case scope |
|---|---|---|---|
| `400-00151`, `400-00151N` | Affidavit in Support of Relief from Abuse Complaint | Affidavit | Initial; Family / Relief from Abuse |
| `400-00151M` | Affidavit in Support of Relief from Abuse Complaint for Child | Affidavit | Initial; Family / Relief from Abuse on Behalf of a Minor |
| `DPS-132` | Protection Order Service Information | Protection Order Service Information DPS #132 | Initial; Family / adult or minor RFA |
| `400-00156` | Confidential Notification for Relief from Abuse | Relief from Abuse Litigant Address Form | Initial; Family / adult or minor RFA |
| `400-00813A` | 813A Financial Affidavit | 813A Financial Affidavit | Stage not specified; Family |
| `400-00813B` | 813B Financial Affidavit | 813B Financial Affidavit | Stage not specified; Family |
| `600-00264` | Certificate of Service | Certificate of Service | Stage not specified; Family/Civil |
| `400-00831` | Notice of Pro Se Appearance | Notice of Pro Se Appearance | Stage not specified; Family |
| `400-00800` | Family Court Information Sheet (Form 800) | Information Sheet | Stage not specified; Family |
| `400-00849` | Statement of Confidential Information | Statement of Confidential Information | Stage not specified; Family |
| `600-00228` | Application to Waive Filing and Service Fees | Application to Waive Filing and Service Fees | Stage not specified; Family/Civil/Probate |
| `100-00127` | Small Claims - Financial Disclosure Affidavit | Small Claims - Financial Disclosure Affidavit | Subsequent; Civil |
| `100-00128` | Small Claims - Disclosure of Exempt Income | Small Claims - Disclosure of Exempt Income | Subsequent; Civil |
| `400-00150C` | Complaint for Relief from Abuse | Initial Filing | Initial; Family / Relief from Abuse |
| `400-00150CC` | Complaint for Relief from Abuse on Behalf of Child | Initial Filing | Initial; Family / Relief from Abuse on Behalf of a Minor |
| `100-00257` | Small Claims Complaint | Initial Filing | Initial; Civil / eight audited Small Claims types |
| `VDH-VR-DIV`, `VDH-VR-DISS` | Vital Records divorce/dissolution forms | — | Stage not specified; Family; unmapped |
| `100-00260` | Small Claims Certificate of Service | Certificate of Service | Stage not specified; Civil |
| `100-00265` | Notice of Appearance for Self-Represented Party | Notice of Pro Se Appearance | Stage not specified; Civil |
| `100-00126` | Small Claims Answer | Answer | Subsequent; Civil / eight audited Small Claims types |



## Source inventory versus rendered-document tests

The [guided interview inventory](../../efile_app/efile/data/guided_interview_inventory.json) and its Illinois/Vermont manifests are repository/source inventories. They help back the dynamic Illinois alias parity check but do not show that every interview ran or every attachment rendered to PDF in this test suite. The PDF extraction test above uses mocked PDF text for four IDs. No assertion in this inventory should be interpreted as full generated-PDF execution coverage.
