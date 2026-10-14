# Agentic filing-code search

The hierarchical document classifier now handles its existing
`request_more_candidates` response by running the same indexed path search as
Find code. A model can choose a query, read the results, refine the query, and
then select a live candidate or abstain. This addresses
[#295](https://github.com/SuffolkLITLab/LITEFile/issues/295) without requiring a
different LLM provider API: tool requests use the existing JSON response
protocol. The implementation is in `classification_search.py` and
`HierarchicalDocumentClassifier._select`.

The application fixes the jurisdiction, selected court, initial/subsequent
stage, and previously selected category/type. Search is unavailable during
court selection or when the stage is unknown. Each hierarchy node allows two
searches and three model responses at most. Empty, malformed, oversized, or
repeated queries stop with abstention. Queries are limited to 200 characters;
the prompt asks for form identifiers/titles or filing purpose without personal
details. Queries are not added to classification metadata or application logs.

Search reads the current local index for the configured provider and rules
digest. It never refreshes the catalog during extraction. Results are capped
at ten distinct candidate references from a window of fifty paths and include
explanatory source links and the index refresh time. The classifier skips the
full result count and display-only glossary/guidance work. PostgreSQL statements
have a two-second timeout (or an existing stricter timeout); the previous
setting is restored. Failed queries roll back inside a savepoint.
An unavailable index or database error causes abstention. A result must match
the live candidate's exact code and name to receive a selectable reference;
disabled paths are excluded. Cached labels remain advisory, and returned
references are checked against the original live candidate list. Existing
downstream filing validation still applies. Search cannot introduce a new
provider code or establish that two forms are equivalent.

Classification metadata records `code_search_protocol: v1` and the number of
search rounds. Successful direct classification performs no search. A full
run can add at most six searches and six model requests across category, case
type, and filing type. The existing taxonomy prompt version remains recorded
separately from this appended search protocol.

## Crosswalk reconciliation

The August 28 Vermont partner workbook linked in
[#325](https://github.com/SuffolkLITLab/LITEFile/issues/325) was downloaded and
compared with the current registry on October 14, 2026. Its SHA-256 is
`1db8a2930e177ed2725c81eb2fb58b0ff8cd85d6d5b8d8d64a9f6bd84145e9e2`.
The substantive initial/subsequent mappings already existed on main; see the
[crosswalk verification record](filing-code-crosswalk-verification.md).

Rows 19–20 use `VDH-VR-DIV` and `VDH-VR-DISS` without the revision suffixes in
the stored form identifiers. These now resolve as identity aliases. Both
filing-code cells are question marks, so no mapping was added. Runtime and
benchmark registries remain byte-identical. Complaint/answer stage separation,
unresolved divorce qualifiers, and other existing association safeguards remain
in effect. Partner confirmation of uncertain mappings remains separate work.

## Validation and deployment

Tests cover actual indexed search with competing courts, stages, categories,
case types and stale codes; provider/rules mismatches; renamed and disabled
filings; model query refinement; malformed/repeated requests; bounded rounds;
unavailable search; and invented references. These are deterministic integration
tests, not a measured claim of improved model classification accuracy.

Claude reviewed the implementation and found no blocking correctness bugs.
Its recommendations led to skipping counts and display-only serialization,
the query timeout, deduplicating candidate references, and end-to-end classifier
scope tests. Smaller suggestions also removed the unused YAML round-limit
setting, disabled search instructions at unsupported nodes, trimmed queries
before length checks, and fixed CSV line endings and leading country codes.
Unexpected programming errors are deliberately not swallowed by a broad
exception handler; database failures are handled explicitly.

The available local environment has no current Illinois search index, so a
representative staging latency measurement was not obtained. The timeout and
bounded query tests do not substitute for a full-catalog performance benchmark.

Deploy with the usual application restart and an existing filing-code index
for each jurisdiction. No schema migration or search-index rebuild is required
by this change. If an index is absent, use the existing
`refresh_filing_code_index` management command. Court contacts are compiled
configuration with no new runtime data dependency.
