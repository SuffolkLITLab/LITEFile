# Form search relevance benchmark

This replay measures whether known form identities and aliases retrieve the intended complete e-filing path. It compares baseline commit `47f6afca2177625adf68cdf0d16194fc6ab951b0` with the working tree on October 13, 2026.

The benchmark uses the actual `efile.services.filing_code_search.search_paths` function with isolated SQLite databases. Its frozen fixture has 24 curated paths (16 Vermont and 8 Illinois) and 22 queries (16 Vermont and 6 Illinois). It uses captured provider filing labels and synthetic assembled court/category/type contexts; it does not claim that every complete path is offered by a live court catalog. Non-court fixture facet codes are opaque numeric values; semantic fixture IDs are mapped to result rows outside the indexed search text. Vermont RFA paths are queried by printed form IDs and plain-language phrases (“complaint,” “relief from abuse complaint,” and “start relief from abuse case”), alongside a stage mismatch, unknown IDs, and a cross-state negative. Illinois examples cover ATJ form numbers, family-only/category scope, Cook County scoping, and unknown/cross-state negatives. The fixture also checks an exact Vermont fee-waiver provider label in Civil, Family, and Probate contexts at both initial and subsequent stages; the Probate row guards against a scoped alias hiding the same exact label outside Civil/Family, but does not assert live case-type coverage. A Vermont exact-label query is included as a sanity control. The fixture records its limitations and is not a full-catalog or legal-coverage test.

| State | Revision | Positive queries | Top 1 | Top 5 | Mean recall@5 | Negative no-result |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Illinois | `47f6afc` baseline | 4 | 0/4 (0%) | 0/4 (0%) | 0% | 2/2 (100%) |
| Illinois | working tree | 4 | 4/4 (100%) | 4/4 (100%) | 100% | 2/2 (100%) |
| Vermont | `47f6afc` baseline | 14 | 3/14 (21.4%) | 3/14 (21.4%) | 21.4% | 2/2 (100%) |
| Vermont | working tree | 14 | 14/14 (100%) | 14/14 (100%) | 100% | 2/2 (100%) |

All 14 intended Vermont working-tree queries and all four Illinois working-tree queries rank a relevant result first. The Vermont baseline hits were the exact `Certificate of Service` control and the two exact fee-waiver-label checks. Both exact fee-waiver queries retrieve all three expected Civil, Family, and Probate test paths in the working tree at top five for both stages. These collision paths are synthetic, so the result tests search behavior rather than real provider eligibility. The two negative Vermont and Illinois queries each return no paths on both revisions.

Full per-query rankings, result counts, and corrected terms are in the paired JSON artifacts: [baseline results](fixtures/form-search-relevance-baseline-47f6afc-2026-10-13.json) and [working-tree results](fixtures/form-search-relevance-working-2026-10-13.json). The replay definition is [the frozen fixture](fixtures/form-search-relevance-replay-2026-10-13.json), and the executable is [the benchmark script](../../benchmarking/promptfoo/scripts/benchmark_form_search_relevance.py).

The runner builds rows using the old revision's `_court_entries` indexing logic when `indexed_path` is unavailable; on the working tree it uses `indexed_path`. This fallback materializes each revision's facet tokens, code tokens, and explanation fields. This keeps search inputs consistent with each revision's own indexing behavior. The spelling-correction vocabulary also follows each revision's production index builder and includes words from applicable concept terms. The benchmark intentionally calls ungrouped `search_paths`; the Find code UI uses grouped results, so these figures measure path retrieval rather than rendered UI grouping. Results measure relevance only, not latency, full-catalog coverage, or user decision quality.

Reproduce from a checkout with the project environment installed. Use new, nonexistent database paths; the runner refuses to overwrite an existing database.

```bash
cd efile_app
uv run python ../benchmarking/promptfoo/scripts/benchmark_form_search_relevance.py \
  --revision working-tree \
  --database /tmp/form-search-working.sqlite \
  --output /tmp/form-search-working.json
```

For the baseline, create a separate checkout or archive of commit
`47f6afca2177625adf68cdf0d16194fc6ab951b0`. That commit does not contain this
runner or fixture: use the script and fixture from this PR unchanged. From the
baseline's `efile_app` directory, set `PYTHONPATH` to that directory, invoke the
project environment's Python with the absolute path to this PR's runner, and pass
`--fixture` with the absolute path to this PR's frozen fixture. Use a different,
nonexistent database path and `--revision HEAD-47f6afc`. Setting `PYTHONPATH`
ensures the baseline application code wins over an editable installation of the
working tree.
