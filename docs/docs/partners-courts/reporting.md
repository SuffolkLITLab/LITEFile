---
id: reporting
title: Interpret aggregate usage reports
sidebar_label: Usage reports and metrics
---

# Interpret aggregate usage reports

These definitions describe the analytics implemented through #318 at the October
13, 2026 audit. Reporting access is scoped by jurisdiction; use the
[analyst onboarding path](../admin/staff-onboarding.md#aggregate-reporting-onboarding).
Collection and export default off and need separate policy/operations approval.
The internal [runbook](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/staff-privacy-and-analytics.md)
remains the technical reference.

## Metrics dictionary

| Metric | What is counted | Interpretation limit |
| --- | --- | --- |
| `started` | Once per owned draft created or first handoff claim | Excludes unclaimed handoffs; drafts are not people |
| `review` | Once per draft reaching validated Review | Does not establish submission or court acceptance |
| `submission_attempt` | Once per logical submission operation | Repeated clicks/transport retries do not create extra attempts |
| `transmitted` | Once per draft with confirmed delivery to the filing service | Delivery is not court acceptance |
| `submission_error` | Confirmed pre-call failure/API rejection per operation | Ambiguous outcomes are excluded; absence does not establish success |
| `document_uploaded` | Once per document row, with preparation/form-field dimensions | Replacements/documents are not unique legal forms |
| `documents_transmitted` | Document rows in confirmed transmissions | Not a count of distinct form types |
| `pages_transmitted` | Pages when every document's extraction page count is known | Omitted when incomplete; not zero-page filing |
| `guided_forms_transmitted` | Transmitted documents with an interview-supplied form name | Excludes forms removed before sending |
| `matter_first_used` | First confirmed transmission into a known matter for a local account | Per-account matter identity; not unique court cases across people |
| `court_accepted` | Once per LITEfile filing ID observed accepted in current court status | Observed when an authenticated filer views status; no automatic outcome poll |
| `court_returned` | Once per LITEfile filing ID observed rejected or returned | Multiple filings can belong to one submission |
| `rejection_reason` | Once per returned filing whose detail was viewed, reduced to fixed category | Clerk free text is classified in memory and never stored in analytics |
| `draft_discarded` | Once per explicit discard of an unfinished draft | Session expiry is not a discard |
| `draft_resumed` | Each resume from the drafts page | Repeat resumes can exceed draft count |

Events use UTC date, configured jurisdiction and new/existing/unknown stage as
recorded at the time; later changes do not rewrite history. Contributor counts
are distinct **local accounts per cell**, not distinct human beings. One person
can have accounts in different jurisdictions; an account can file for others.
Only submitted LITEfile drafts contribute observed court outcomes.

Detailed monthly reports give independent breakdowns for configured case type,
filing code, court, filer side, attorney representation, filing for self/someone
else, waiver use, interview source, workflow step, categorized return reason,
five-digit filer ZIP, preparation outcome, original PDF form fields and
first/2–5/6+ transmission frequency. They do not combine ZIP and case details
into a person-level row. Unknown answers stay unknown. `no_form_fields` does not
prove a PDF was flattened; Word/legacy-unknown inputs are separate.

Attorney representation is `yes` when an imported court roster links the filer to
a represented party, `no` for a new-case filer selecting themselves, and can be
`unknown` for an existing case without an attorney association. Missing association
is not evidence of no lawyer. Unfamiliar configured case types use
`other_or_unknown`; interview sources are limited to deployment-owned keys.

## Coverage, privacy and suppression

Collection starts at deployment; there is no historical usage backfill. Debug,
stand-in-document deployments, staff and designated test accounts are excluded.
Before a production test, the operator designates the local account with
`exclude_analytics_account ACCOUNT_ID`; already anonymous counts cannot later be
subtracted. Queue/worker failures can delay or omit observations without blocking
the filer. Always include coverage/freshness/pending-work notes.

Core reports use fixed daily UTC buckets; detailed reports require full calendar
months. The default disclosure floor is five distinct contributing local accounts
per cell, configurable upward. A small cell suppresses the entire requested
breakdown/period, including subtotals/rare labels; dashboard and CSV agree.
Do not infer zero activity from suppression or missing coverage. This safeguard
is not a guarantee against identification with outside information.

Permanent aggregate counters contain no account/draft/session IDs, names,
document/clerk text, docket numbers, IP addresses or credentials. They remain
after account deletion. Temporary operational deduplication/outbox data and
backup/provider retention have separate handling; deleting an app record does
not erase all copies. See [privacy onboarding](../admin/staff-onboarding.md).

## Example report interpretation

Illustrative numbers only, not a production report: a complete-month report shows
100 `started`, 60 `transmitted`, and 30 `court_accepted` from 20 contributing
accounts. This means 100 owned drafts started, 60 confirmed transmissions and 30
filing IDs were **observed** accepted. It does not show 20 people, a 50% acceptance
rate, or that the other 30 submissions were rejected. Different cohorts/events,
multiple filings per submission and unviewed outcomes prevent that calculation.
A suppressed ZIP breakdown does not mean nobody filed from that ZIP.

Attach this interpretation record to shared reports:

```text
Jurisdiction / full UTC period / grouping / approved breakdown:
Coverage start / freshness / pending work:
Metrics and contributor threshold:
Test-traffic exclusions / suppressed and unknown data:
Observation limits (especially court outcomes):
Reviewer / sharing approval / evidence location / next review:
```

Assign a reporting owner and policy reviewer in the
[maintenance register](./maintenance.md). Recheck boundaries after analytics
changes, new jurisdictions, policy changes and before external publication.
