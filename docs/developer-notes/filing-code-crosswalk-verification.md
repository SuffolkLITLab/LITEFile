# Filing-code crosswalk verification for Vermont and Illinois

Checked October 13, 2026, for the evidence backlog in [issue #296](https://github.com/SuffolkLITLab/LITEFile/issues/296). This note combines the Vermont interview/code review and a read-only Illinois test-provider audit. The audit records searched options and misses; it does not establish eligible-court coverage or a 90% result.

The [direct test inventory](filing-code-direct-test-inventory.md) enumerates the
filings, query assertions, and observed court scopes, and distinguishes controlled
extraction tests from rendered-PDF execution and catalog availability checks.
The [paired relevance benchmark](form-search-relevance-benchmark-2026-10-13.md)
compares the unchanged baseline with this implementation on a frozen 22-query
replay: top-five retrieval improves from 3/18 to 18/18 positive queries; all four
negative queries return no results in both versions. This small synthetic corpus
measures ungrouped path retrieval, not full-catalog or eligible-court coverage.

Claude's code review identified an exact-label regression, an unscoped Cook-only
form association, incorrectly extracted source titles, and benchmark fixture words
leaking into the search index. The follow-up preserves exact provider-label
searches without broadening form-number aliases, withholds the Cook-only
`CCDR 0019 A` association pending court-specific evidence, corrects the printed
titles, and reruns the benchmark with opaque numeric fixture codes and the
production spelling vocabulary. Regression tests also preserve independently
audited Initial Filing mappings during reconciliation. The exact-label fallback
currently requires the complete provider label as the query; adding court words
to that text can still require selecting the court through the search filters.
Follow-up tests also verify that the default strong-match view shows both an
exact label and its supported synonym, and that shared statewide/Cook source
records reconcile identically regardless of inventory order.

## Vermont: new Relief from Abuse cases

For a new Vermont Family case, the Judiciary’s Family e-filing guide names **Initial Filing** for the complaint and other initiating documents. It lists the relevant case types as **Relief from Abuse**, **Relief from Abuse on Behalf of a Minor**, and **Relief from Abuse, Neglect and Exploitation**. The Judiciary’s FAQ separately confirms Initial Filing for new Civil, Probate, and Family cases, and describes different codes for other divisions. The supported search intent is therefore a new Family RFA case, with the actual case type selected and the initial stage preserved. This mapping must not apply to subsequent filings in an existing case or to Criminal or Environmental filings.

Sources: [Vermont Judiciary File & Serve FAQ](https://www.vtcourts.gov/about-vermont-judiciary/electronic-access/electronic-filing/faqs), [Family Division e-filing guide](https://www.vtcourts.gov/media/12013), [Civil Division e-filing guide](https://www.vtcourts.gov/media/12012), and [Environmental Division e-filing guide](https://www.vtcourts.gov/media/12405). The repository’s Vermont Tyler snapshot contains the corresponding Family/RFA case types and Initial Filing entries, but its filing rows have blank category and case-type IDs; it is not a current live mapping. The partner workbook attached to [issue #325](https://github.com/SuffolkLITLab/LITEFile/issues/325) is supporting evidence for interview outputs and proposed code labels, with several unresolved or internally inconsistent rows.

## Illinois: eviction court-file removal

Illinois’s standardized form is titled **Motion to Remove Eviction Court File from Public Record**. Its paired order is **Order to Remove Eviction Court File from Public Record**. The official form and [735 ILCS 5/9-121](https://www.ilga.gov/documents/legislation/ilcs/documents/073500050K9-121.htm) connect this plain-language request to sealing an eviction action court file. The Illinois Courts explain that “remove … from the public record” was chosen in place of “seal” for plain-language access, and confirm ILAO published guided interviews for the motion. [ILAO’s Easy Form page](https://www.illinoislegalaid.org/legal-information/remove-eviction-public-record) says the interview prepares the motion, notice, proof of delivery, order, and instructions; it does not e-file them.

Useful query wording includes `remove eviction from public record`, `remove eviction court file from public record`, `seal eviction case`, `eviction record sealing`, and `hide eviction case from public record`. Keep the mapping limited to the Illinois eviction-record-removal intent and an existing case. Do not treat criminal expungement, generic redaction, a motion to dismiss/vacate, or an eviction answer as equivalent. ILAO also cautions that third-party tenant-screening reports may still show a sealed case.

The live test-provider audit queried all **360** court codes returned by the Illinois court-list endpoint. All 360 subsequent filing-option requests succeeded and returned 784,189 rows total; the exact motion title appeared in **zero** court responses. A targeted scan of subsequent paths under Civil, Eviction, Housing, or Forcible categories found 855 eviction-related case-type rows across the 360 courts and no exact-title path. This is a catalog retrieval result, not an eligibility denominator.

For DuPage, the live catalog includes the **Eviction** category and subsequent case types **Change of Venue - Eviction**, **Residential**, **Residential - Possession Only**, plus eviction cases under Law and Law Magistrate categories. The checked type-specific paths did not include the exact motion. They included **Motion for Redaction & Confidential Filing**. Cook County Municipal Civil (District 1) eviction paths included **Filed Under Seal** and **Motion To Redact Filed**. These labels may concern record confidentiality or redaction, but the available official form/statute sources do not establish that they request sealing the entire eviction court file. They remain unverified alternatives and must not be presented as equivalent based on label similarity.

A historical repository snapshot (`benchmarking/promptfoo/data/tyler_catalog/illinois/catalog.json`, commit `179b2d8`, August 23, 2026) contains four DuPage subsequent rows titled **Motion to Remove Eviction Court File from Public Record** (codes `309683`, `309736`, `309746`, `309756`). Each has blank `casecategory` and `casetypeid`; none appeared in the October 13 live responses. Treat these as historical catalog evidence only until reconciled with a refreshed provider snapshot or code-steward confirmation. Do not map a generic Motion filing to this request.

Sources: [Illinois Courts eviction forms](https://www.illinoiscourts.gov/documents-and-forms/approved-forms/eviction/), [Illinois Courts announcement on the plain-language form](https://www.illinoiscourts.gov/News/1393/New-eviction-form-sets-enhance-access-to-justice-for-selfrepresented-litigants-in-Illinois/news-detail/), [standardized motion PDF](https://ilcourtsaudio.blob.core.windows.net/antilles-resources/resources/5f8fb145-e549-4cce-a468-d18e7c638f67/REF%20Motion.pdf), and [ILAO overview of eviction records](https://www.illinoislegalaid.org/legal-information/what-happens-if-i-have-eviction-my-record).

## Audit provenance and limits

The dated machine-readable results are in [illinois-eviction-record-removal-audit-2026-10-13.json](fixtures/illinois-eviction-record-removal-audit-2026-10-13.json). The environment was `efile-test.suffolklitlab.org`. The provider returned an HTTP `Date` header, but no catalog version or snapshot identifier in the inspected response headers or payload. The audit lists every court code/name, option count, exact-title count, and request errors. It does not contain the full catalog. A read-only live Vermont initial-code catalog audit is appended below. Neither state audit establishes an all-court eligible-path denominator.

## Vermont live catalog audit: initial filing availability

On October 13, 2026, the live test catalog was queried read-only at `efile-test.suffolklitlab.org`. The request sequence matches the application’s `CodeCatalog`: fetch initial, fileable categories; fetch each category’s case types with `timing=Initial`; then request filing types with `initial=true`, the selected category ID, and the selected case-type ID. Only the exact case-sensitive filing label **Initial Filing** counts. The provider’s response Date headers range from 20:26:29 to 20:26:41 GMT; no catalog version or snapshot ID was exposed.

All **14 county units** returned initial **Family (210)** and the same three RFA types: **Relief from Abuse (6177)**, **Relief from Abuse on Behalf of a Minor (6178)**, and **Relief from Abuse/Neglect/Exploitation (6179)**. For every queried type at every unit, the exact filing option **Initial Filing (9564)** was offered. This is direct availability evidence for those type-specific new-case paths.

The remaining three court-selector options had no initial RFA path: **Environmental Division** returned only **Civil (7)**; **Judicial Bureau** returned no initial categories; **Supreme Court** returned only **Appellate (211)**. No other court-selector option was omitted from the request set. All 17 courts, initial categories, case-type IDs, returned filing-code IDs, per-court applicability, and errors are recorded in the [Vermont machine-readable audit](fixtures/vermont-initial-filing-audit-2026-10-13.json).

The same pass checked Small Claims where available. At all 14 county units, eight initial Civil case types had exact **Initial Filing (9563)**: **Small Claims over $1,001 (7232)**, **Small Claims up to $1,000.00 (7233)**, and the six amount/consumer-credit/medical-debt variants (type IDs differ by county; see the JSON). These are provider timing/category/type options, not a legal eligibility or interview-completeness finding.

This audit establishes only that these exact options were offered by the test catalog for the selected initial paths at the time queried. It does not establish a statewide legal coverage percentage, all-interview completeness, or live production availability. The provider returned no request errors. No forms were submitted and no external state was changed.


## Implementation and remaining work

The indexed aliases preserve provider labels and IDs. Vermont complaint searches
are limited to reviewed initial Family, Small Claims, and eviction case types;
they exclude administrative answer-only cases and foreign-order registrations.
Illinois eviction sealing queries require the exact existing-case record-removal
motion and eviction context. Generic redaction and criminal sealing do not
receive that alias. A missing provider option remains a missing option.

The workbook corrected six existing form identities' candidate mappings and added
the official Small Claims Complaint (100-00257). Child/no-child dissolution rows
conflict with the workbook's case types, so those case types remain unresolved.
Rows 19–20 (vital records) and 43–44 (financial disclosure/exempt income) contain
question marks and were not turned into invented codes. Blank timing cells do
not establish subsequent-only availability. Human association review is still
pending; catalog availability alone does not authorize automatic classification.

Regression tests cover real captured Vermont labels and court IDs, grouped and
individual search, legacy and bulk indexing, stage/category exclusions, Illinois
motion-versus-order/redaction distinctions, and live-selection revalidation with
a test catalog. The captured-path replay has no complete set of competing filing
options and therefore is not a full-catalog ranking or 90% coverage audit.

After deploying, restart application workers and rebuild the Vermont and Illinois
search indexes using `refresh_filing_code_index --rebuild --jurisdiction STATE`.
Publication confirmation, document-finder expansion, partner signoff, and the
full eligible-court top-five search audit in #296 remain follow-up work. The
complete repository/output review queue is tracked below. Reconcile Illinois's missing motion with the code steward before assigning
any alternative provider filing code.

## Full issue inventory and both matching surfaces

The issue's complete repository queue is now tracked in
`efile/data/guided_interview_inventory.json`: 26 Vermont repositories and 91
Illinois repositories. Three pinned source manifests record each declared
attachment, its template, printed identifier where supported, publication
status, filing disposition, proposed label, and unresolved evidence. Repository
review is not proof that every interview is currently published. Bundles,
individual documents, split-page fragments, instructions, letters, and other
tribunals remain separate dispositions; output counts are not counts of unique
court forms.

Both matching surfaces consume this work:

- **Extract text:** `form_code_crosswalk.json` identifies printed form numbers
  and supplies advisory filing-label suggestions to the existing deterministic
  scan and AI-assisted extraction pipeline. Its runtime and benchmark copies
  remain identical. A source identity without a supported mapping stays
  unmapped.
- **Find code:** reviewed Vermont form phrases are path-only concepts in
  `filing_code_search.yaml`. Illinois printed-number aliases are generated in
  `guided_form_search_aliases.json` from exact source-title/provider-label
  observations. They augment real indexed paths, preserve provider names and
  codes, retain stage and source scope, and do not create codes. The supplemental
  file participates in the index digest and supplies sourced display text.

The three GPT-6 Luna reviewers inspected the source repositories and templates.
A second review corrected misleading PDF text extraction: certificate headings
inside notices, repeated financial-affidavit headings on distinct schedules,
wrapped court captions, and split motion pages. Split-page components cannot
independently introduce a form identity or filing-code association. Composite
bundles remain inventoried but need document-level treatment.

The read-only catalog pass fetched both initial and subsequent filing-option
lists for all 360 Illinois and 24 Vermont provider-listed court codes (768
requests, no request errors). This includes provider headings and differs from
the 17 Vermont UI selector entries used in the selected-path audit above. The
retained [label observations](fixtures/guided-form-label-observations-2026-10-13.json)
contain only exact source-title matches needed for reconciliation. They record
court codes, stages, labels and provider IDs. These unfiltered option lists do
not establish case-category/type compatibility or an eligible-court denominator.
The environment was `https://efile-test.suffolklitlab.org`; requests used
`/jurisdictions/{state}/codes/courts/{court}/filing_types/?initial={true|false}`.

Run the inventory audit from `efile_app`:

```bash
uv run python manage.py audit_guided_interview_forms --output /tmp/guided-form-coverage.json
```

The full report lists each output's registry identity, runtime suggestions, and
exclusion reason. A passing inventory audit means every queued repository has a
traceable review record, not that every generated document has a verified code.

Reconcile source identities and exact-title observations from the repository root
(first omit `--apply` to review the change report):

```bash
python benchmarking/promptfoo/scripts/reconcile_guided_interview_forms.py \
  --label-index docs/developer-notes/fixtures/guided-form-label-observations-2026-10-13.json \
  --reviewed-associations docs/developer-notes/fixtures/vermont-supporting-form-labels-2026-10-13.json \
  --reviewed-associations docs/developer-notes/fixtures/illinois-reviewed-form-labels-2026-10-13.json \
  --reviewed-associations docs/developer-notes/fixtures/illinois-cook-guided-form-label-audit-2026-10-13.json \
  --report /tmp/guided-form-reconciliation.json --apply
```

Unresolved work includes confirming publication where only repository metadata
is available, resolving dynamic/bundled outputs, partner review of associations,
and checking/ranking complete paths across eligible courts. Some source YAML
files contain tabs or malformed blocks and required attachment-level inspection;
static inventories do not prove that every conditional runtime branch succeeds.
The 90% discoverability requirement is **not established** by these audits.

## Cook County vocabulary and scope

Cook County's provider categories and filing labels cannot be inferred from
other Illinois counties. The [selected-path comparison](fixtures/illinois-guided-form-path-audit-2026-10-13.json)
checks DuPage, Cook Domestic Relations, and Lake against their actual category
and case-type options. Missing exact labels remain missing; a different Cook
label requires a separately reviewed association.

Local path synonyms support exact `court_codes` and anchored
`court_code_prefixes`. Label aggregation includes the indexed vocabulary in its
key, so identical names with different local aliases retain distinct court
sets. This works for ordinary refreshes, incremental updates, and bulk label
rebuilds. The changed index digest forces rebuilding existing label groups.
Extraction keeps the corresponding court scope and filters advisory mappings
once the classifier selects a court and parent category/type.

The [Cook associations](fixtures/illinois-cook-guided-form-label-audit-2026-10-13.json)
retain observed district codes and separate fee/no-fee variants for appearance
and jury requests, plus Financial Affidavit Filed. Cook Domestic Relations
category aliases add “family” only to case vocabulary, based on the
[Circuit Court’s division description](https://www.cookcountycourtil.gov/division/domestic-relations-division).
They do not rename categories or change document identity.

## Coverage after reconciliation

The [per-output coverage sheet](fixtures/guided-form-coverage-2026-10-13.csv)
contains all 859 inventoried output rows, with source links, exclusions,
publication status, identifiers, and runtime filing-label suggestions. Its
[summary](fixtures/guided-form-coverage-2026-10-13.json) separates documents,
bundles, and fragments.

| State | Repositories reviewed | Individual court-document rows | Rows with advisory runtime mappings | Rows without runtime mappings |
| --- | ---: | ---: | ---: | ---: |
| Vermont | 26 | 45 | 32 | 13 |
| Illinois | 91 | 288 | 63 | 225 |

These are **output rows**, including repeated forms across interviews, not
unique forms or eligible courts. The remaining court documents are not silently
counted as covered. The inventory also includes Illinois bundles and fragments
that need separate treatment. Court mappings remain advisory pending human
association review and court-specific selection.

The global registry structural audit still reports 987 pre-existing entries
missing `form.is_efileable`, the same issue count present at the starting commit.
The reconciled records add no structural violations; the runtime and benchmark
registry files are byte-identical.
