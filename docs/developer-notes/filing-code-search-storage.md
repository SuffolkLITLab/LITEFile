# Filing code search storage

Notes on why the filing code search tables are as large as they are, what was decided on 2026-10-10, and where to look first if the database needs space.

## Where the space goes

Measured on `litefile-staging` (Supabase Postgres) on 2026-10-10. The database was 7.7 GB, and `efile_filingcodepath` was 7.6 GB of it. Each row is one real court › category › case type › filing type path.

| Jurisdiction | Stage | Paths | Distinct filing/category/case-type labels |
|---|---|---|---|
| Illinois | New case | 922,059 | 43,382 |
| Illinois | Existing case | 10,704,264 | 763,175 |
| Massachusetts | New case | 110,513 | 9,049 |
| Massachusetts | Existing case | 348,289 | 30,798 |
| Vermont | New case | 335,133 | 22,748 |
| Vermont | Existing case | 770,186 | 52,277 |

Existing-case paths are about 88% of the rows, and Illinois existing-case paths alone are about 80%.

The database also had little free disk. A `COUNT(DISTINCT …)` over the table failed with "No space left on device" when its sort spilled to temporary files.

## Labels

Search reads labels first (`services/filing_code_labels.py`). Each label is one row however many courts share it, so the table is a fraction of the paths table. A synthetic Illinois-shaped test came to about 63 MB per 100,000 labels, indexes included, so Illinois's 806,000 labels should take about 0.5 GB.

## Decision: keep existing-case search

We keep existing-case paths in the search index for now, even though a filer with an existing case now chooses a filing type from the live list for their confirmed case (`services/case_filing_types.py`).

Existing-case search helps filers notice that they chose the wrong kind of case on the opening menu. The finder's "New case / Existing case" toggle, and its count of matches in the other stage, point them to the right path instead of a dead end. Whether a filing starts a case or goes into an existing one is not always obvious to filers.

## If we need the space later

In rough order of savings:

1. **Drop existing-case paths from the index.** This removes about 88% of `efile_filingcodepath`. The finder would lose its existing-case toggle and the other-stage hint, so the wrong-case-type problem above would need another answer, such as a check on the opening menu. Existing-case filing types already come from the live EFSP list.
2. **Keep existing-case labels, drop existing-case paths.** `FilingCodeLabel` holds one row per filing/category/case-type name combination, with a map of the courts that offer it and how many paths each has. The finder's groups, court lists and other-stage count are read from labels; only the final case-type step reads full paths. For an existing case, that step could use the live EFSP lists for the chosen court instead.
3. **Normalize `FilingCodePath`.** Move the court, category, case-type and filing-type JSON into lookup tables and keep integer keys on each path. This shrinks every row but touches the sync and every reader of `path.court` and the other facets.

Rewriting the table in place (a backfill `UPDATE` or a full rebuild) temporarily needs about as much free disk again, until vacuum reclaims it. Check free disk first, or delete in batches and vacuum between them.
