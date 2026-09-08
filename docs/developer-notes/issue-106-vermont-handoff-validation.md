# Vermont interview handoff validation

Validated on September 8, 2026, using synthetic answers in the running local
Docassemble server, the installed `docassemble.RFApackage`, an isolated LITEFile
SQLite database, private LocalStack S3 storage, and the dev EFSP's live Vermont
court metadata. No filing was sent during the initial pass. The later dev
submission is documented below.

## Implementation exercised

The adapter was installed with:

```bash
~/venv/bin/dainstall --server localhost ~/docassemble-RFApackage
```

The interview was completed with synthetic adult RFA answers through the
Docassemble session API and browser. It generated four actual court PDFs:
complaint, affidavit, confidential contact information, and service information.
The next-steps instructions were excluded from the transfer.

Playwright exercised the browser handoff, ownership claim, missing-details
screen, document checklist, document classification form, and return to the
interview. The Docassemble API supplied and changed substantive answers; PDF
creation and transfer ran in the installed interview.

## Observed results

- The source-authenticated multipart handoff created one durable draft with four
  privately stored PDFs. Repeating the transfer from the interview succeeded
  without another receipt, draft, or document set.
- Claiming the draft resolved Chittenden Unit, the Family category, the adult
  Relief from Abuse case type, plaintiff/defendant party types, and three
  supporting filing types against live Vermont metadata. Filer and party names
  and contact information were prefilled.
- The source's `Complaint` hint had no unique live filing-type match. LITEFile
  left it editable. Browser selection of a dev filing type, confidentiality,
  and components saved successfully and returned directly to the handoff
  screen. Only payment/fee work remained in the missing-details list.
- A simulated submitted outcome and confirmed clerk return created a correction
  revision through the actual correction view, with only the court detail
  fetch/response mocked. The previous submission snapshot, parties, document
  references, and filing choices were preserved.
- The browser returned to the same Docassemble session using the scoped
  correction link. An updated synthetic incident description generated new
  PDFs and transferred them to the same correction draft. All four storage
  references changed; filing types, confidentiality, and components remained
  unchanged. Text extraction from the stored replacement affidavit confirmed
  the corrected incident description, rather than merely a changed PDF hash.
- A second simulated clerk return targeted the lead filing type. The correction
  draft retained the PDFs and supporting classifications. Repairing the lead
  classification in the browser cleared the correction requirement without
  rerunning the interview.
- Automated tests cover partial handoffs, authentication and ownership,
  idempotency, invalid schemas and hashes, provenance, ambiguous/partly accepted
  outcomes, immutable snapshots, correction/replacement retries, same-matter
  grouping, expiring claims, unclaimed retention, targeted navigation, and
  renewed private document URLs. Sender tests include adult/minor case hints.

The temporary test configuration and scripts contain credentials or private
session links and are deliberately outside the repositories. The dev server
uses an isolated database; synthetic submission outcomes were not added to the
ordinary development database.

## Bugs fixed during validation

- The claim screen's `no-referrer` policy caused a browser form submission with
  `Origin: null`, which Django rejected. Same-origin referrers permit CSRF checks
  while suppressing referrers on the external interview return.
- Regenerating PDFs for a retry changed PDF timestamps and hashes. The interview
  now retains AssemblyLine's cache, payload, and `DAFile` handles per transfer,
  without making independent frozen copies.
- The first cache implementation caught Docassemble's `DAIndexError`, which is
  how Docassemble asks the attachment block to assemble an undefined final PDF.
  Letting that exception propagate allows all four attachments to resolve.
- An event-only `BackgroundAction` wait returned to the host interview's
  download screen before consuming its result. A generic initial routing block
  now resumes pending uploads before the host interview's mandatory blocks run.
- A document-content correction incorrectly also displayed “Add the main PDF”
  for an existing lead document. Missing-lead and replacement requirements now
  have separate paths.
- Durable imported PDFs now receive fresh private URLs when resumed instead of
  relying on the signature saved during the original handoff.
- Malformed return URLs produce a validation error instead of an unhandled
  parser exception.

## Verification limits

The configured Vermont sign-in request returned upstream HTTP 500 with
`jakarta.xml.ws.WebServiceException: Could not send Message`. Browser ownership
and editing therefore used a synthetic local authenticated session. Court
metadata requests used the live dev service; court submission and clerk status
were not live-tested. Clerk outcomes were explicitly simulated through the
correction view. The environment's `EFSP_TEST_DOCUMENT_URL` override was active,
so a dev fee quote or submission would also use the configured stand-in PDF.

A real authenticated fee/review/submission/status check remained outstanding
at the end of the initial pass; see the credential retry below. The adult interview was exercised on the server; the
minor-specific semantic hint was verified by a sender unit test.

## Final automated checks

- LITEFile: `uv run pytest -q` — 782 passed.
- Vermont sender: `python -m pytest -q tests/test_litefile.py` — 16 passed.
- LITEFile: `uv run ruff check .` and `uv run ty check` — passed.
- Django: `makemigrations --check --dry-run` — no model drift; migration 0023
  was applied to the isolated test database.
- Public documentation: `npm run build` — passed.
- Both repositories: `git diff --check` — passed.

## Updated Vermont credential retry

After the Vermont-specific password was updated, the requested Luna subagent
retried authentication and received HTTP 200. LITEFile authenticated the real
Vermont account. A fresh dev handoff containing one synthetic PDF was claimed
by that account and reached the handoff review hub, resolving Chittenden Unit
and Relief from Abuse against live metadata. The local database confirms that
this draft has a different owner from the earlier synthetic login, remains
editable, and has no submission response.

The sign-in blocker is resolved. This retry verifies real authentication and
ownership claim; it does not establish fee calculation, submission, or court
acceptance. No court submission was made in this retry.

## Authorized dev submission

After explicit authorization to submit to the dev server, the installed
Docassemble interview prepared a fresh source identity and transferred all four
court PDFs into a new draft. Each private storage object matched the source's
SHA-256 hash. The real Vermont account claimed the draft and completed live
metadata selection, payment, and final review.

- Confirmed proxy host: `efile-test.suffolklitlab.org`.
- Quoted fee: $14.40 using the saved test VISA payment method.
- One submission succeeded; the draft persisted as `submitted`, with an
  immutable submission snapshot, case ID, envelope ID, and four filing IDs.
- The dev filing-status list returned HTTP 200. Individual detail queries
  initially returned `submitted` for two filings; the other queries were
  temporarily unavailable or timed out. Read-only retries confirmed the other
  two as `submitted`, with matching filing IDs. All four filings are now
  confirmed submitted. The submission itself was never retried.
- Browser verification after the fix showed “Your filing was sent to the court,”
  a visible confirmation reference, and four documents sent.
- The dev stand-in PDF setting remained active. Actual interview PDFs were
  generated, transferred, and verified in LITEFile, while the remote proxy
  fetched the configured stand-in PDF for each submitted document. This test
  demonstrates the dev filing transaction, not clerk acceptance or review of
  the actual RFA document contents.

The real response exposed two bugs that were fixed: `filingIds` lists now link
submitted filings to their draft, matter history, and correction flow; and the
confirmation screen uses `envelopeId` as its confirmation reference instead of
missing it or displaying a nested contact ID. Regression checks passed:
55 handoff, review/submission, and filing-integrity tests, plus Ruff and type
checks. The final full suite passed 782 tests, including these regressions.

## Declarative adapter cleanup

The final adapter moves all interview customization into `litefile.yml`:
source variable paths, adult/minor case hints, party
roles, per-document filing/document/component hints, configuration lookup, and
navigation. The main RFA interview only includes that YAML and displays its
`litefile_continue_button` template. The reusable Python module contains no RFA
or Vermont branches, variable names, document mappings, or classifications.

PDF handling now retains AssemblyLine's `get_cacheable_documents()` result per
transfer. It no longer creates separate frozen DAFile copies. The payload and
cached file handles are reused on retry; a new correction token obtains a new
AssemblyLine cache.

Installed the refactored adapter on the running Docassemble server and verified:

- Four actual PDFs transferred through `BackgroundAction` into one new draft,
  and the success screen appeared after one click.
- Retrying returned HTTP 200 and preserved one receipt, draft 10, the same
  source identity, and four documents.
- A substantive answer edit and correction transfer replaced all four PDFs in
  that same draft while preserving its filing metadata.
- Retrying the correction kept one replacement receipt and two total transfer
  caches (initial and correction).
- Text extraction from the stored affidavit confirmed the new correction text.
- Sixteen adapter tests, Ruff, whitespace checks, and the documentation build
  pass.

The reusable person helper defaults to the standard AssemblyLine and
Docassemble name, address, email, and phone attributes. An interview can pass a
keyword-only `fields` mapping for different object shapes and tests can replace
`showifdef` through the keyword-only `known` argument.

The final live retry used the flat `litefile` server configuration and logged an
empty argument mapping for `litefile_upload`. Credentials, correction tokens,
and interview answers therefore remained outside the background job arguments.

The first attempt encountered a stopped LocalStack container and a recoverable
HTTP 503. Restarting local storage allowed the same cached transfer to succeed.
No additional court submission was made during this refactor validation.
