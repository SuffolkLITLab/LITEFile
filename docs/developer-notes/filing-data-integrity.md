# Filing data integrity

The changes for issues #217 and #218 establish three workflow rules.

## Extraction evidence and parties

Extraction normalization removes whole-value missing answers such as `unknown`, `N/A`, and `not provided`, including inside arrays and objects. Display normalization also covers older saved extractions. It preserves meaningful zero/false answers and names such as “All Unknown Occupants.”

Only captioned plaintiffs/petitioners and defendants/respondents prefill party rows. Other names remain in the supporting evidence disclosure. A filer can explicitly add a person as a party; merely mentioning a child or witness does not add them to the submitted party list.

## Primary filing type

The lead `FilingDocument` owns the primary filing type. `FilingDraft.filing_type_code` and `filing_type_name` are synchronized summary fields. Document saves, lead changes, document deletion, and successful submission keep those fields aligned. Legacy case-data edits write through to the lead document. Migration `0022` repairs existing draft summaries, including submitted filings.

Use model saves when changing document filing types or roles. Bulk updates bypass model synchronization. Supporting documents retain their own filing types. Review and refiling already use the lead document, while draft serialization uses its synchronized summary.

## Draft identity across tabs

Workflow URLs carry `?draft=<id>`. The workflow base template provides that page's identity to `draft-scope.js`, which preserves it in links, forms, browser history, and fetch requests. Fetch calls using a `Request` object carry `X-Filing-Draft` to preserve the request body. Server redirects and JSON redirect URLs retain the identity, including the submitted filing's confirmation page.

Add any new workflow page to `WORKFLOW_VIEWS` in `services/draft_urls.py`. Starting a filing and choosing another draft remain separate navigation actions. The session pointer supports older entry URLs, but reading a draft never falls back to another browser's latest filing. Explicit IDs are checked for ownership, jurisdiction, status, and conflicting parameters before a view runs. Unavailable drafts return HTTP 409; they never select another draft.

Regression checks, from `efile_app/`:

```bash
uv run pytest -q efile/tests/test_filing_integrity.py
npx playwright test --config=playwright.draft-scope.config.js
```

The Python tests cover persisted data and separate/shared sessions. The browser tests cover links, forms, requests, reloads, and two simultaneous contexts using intercepted responses, without an EFSP account or live filing.
