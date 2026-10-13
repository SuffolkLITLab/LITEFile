# Correction copy and submission contract

Issue #107 uses the durable `FilingDraft`, `FilingDocument`, and `FilingParty`
aggregate. It does not restore a session blob or submit from a snapshot.

## Eligibility and navigation

`services/corrections.py::source_eligibility` is shared by filing details, the
CSRF-protected copy POST, and final submission. The source must be an owned,
local, submitted draft with filing identifiers. Every identifier must match a
fresh court response with a normalized `returned` or `rejected` status. An
envelope identifier alone, a failed transmission, missing response, mismatched
identifier, pending outcome, or mixed outcome is insufficient. Comments do not
determine eligibility and are never interpreted as instructions by code.

GET never creates a copy. An owned existing child resumes without consulting
the court; a submitted child links to its filing details. The source row lock,
owner lock and unique `correction_of` relationship permit only one child.
Further corrections link to the immediately preceding submission. Each section
uses `draft` and `return_to=review`, including when two tabs hold different drafts.

## Copy policy

The three `COPY_*_FIELDS` allowlists are the reviewed field policy. A new model
field defaults to its model default until explicitly considered for copying.

| Data | Policy |
| --- | --- |
| Answers | Copy jurisdiction, workflow version, filing path, court/category/type, existing-case identity and snapshot, supplemental answers, amount, notice email, filer role and AI preference. |
| People | Independent rows, stable role/order/primary-key traversal, all names, addresses, contact information, court roster identity, representation and filing-on-behalf choices. |
| Documents | Independent rows; retain owned storage keys, preparation and preview approval for unchanged bytes, descriptions, order, classification, confidentiality confirmation, components, courtesy copies and optional services. Never copy an expiring public URL. |
| Matter and provenance | Retain plan and checklist item associations. Remap document/party prefixes on metadata events, including waiver-purpose provenance. Retain the interview receipt through the predecessor chain. Do not copy upload/update operation receipts. |
| Submission | New public identity, blank operation identity, draft status and Review step. No response, submitted timestamp, snapshot or court-requirement acceptance is reused. |
| Fees | Clear all selected payment fields, quote total/breakdown/fingerprint. A current payment choice and usable quote or confirmed waiver are required by the existing submit guards. |
| Extraction | Preserve answers and rebase confirmed extraction/proposal fingerprints to the copied document IDs. Background extraction jobs are not copied. |
| History | Preserve the source response, answers and existing snapshot. If a legacy source lacks a snapshot, freeze one before copying. Store the confirmed source detail and comments, including the filing association, on the child. |

`full_snapshot` writes `snapshot_version: 1`, with draft fields plus ordered
`documents` and `parties` arrays; datetimes and UUIDs use Django's JSON encoder.
Older snapshots without a version remain readable display/audit data and are
not used to reconstruct a draft. The copy reads current durable source rows.

## Readiness and replacement

Review renders correction blockers instead of redirecting for payment or
preview prerequisites. `correction_readiness` is also called by direct submit.
It includes legacy correction fields, ordinary handoff requirements, current
scoped court codes, case questions, document preview and owned-storage access.
Empty optional code lists are valid; unavailable lists are blockers. Validation
does not erase saved answers. Existing edit services invalidate dependencies
and fee fingerprints when the filing context changes.

Document URLs are renewed from storage keys. Unavailable bytes leave metadata
visible and require retry or replacement. The upload form can replace a specific
owned row, using the usual preparation pipeline, retaining its filing choices
and resetting its preview. Replacement clears obsolete extraction state for a
lead document. Cleanup checks every remaining document reference before deleting
bytes, so the source continues to own its originals. A legacy envelope-wide
`documents` requirement needs both removal of source bytes from the correction
and introduction of replacement bytes; adding an unrelated PDF is insufficient.

A full correction fingerprint is compared under the final claim lock, in
addition to the existing fee fingerprint and preview check, so changes during
remote validation cannot win a stale submission claim. Only a clean draft can
claim submission. Definitive pre-send/API rejection releases the claim;
ambiguous transport failures retain the blocked error state.

## Provider submission semantics and evidence

Corrections use the existing new-filing POST
`/jurisdictions/{jurisdiction}/filingreview/courts/{court}/filings`. Source envelope
and filing IDs stay local provenance; the payload does not invent a provider
resubmission-reference field. Existing-case corrections preserve the confirmed
`previous_case_id` used by the normal case-selection contract.

Source inspection: EfileProxyServer commit
`0ce64d5221497b3996281c745c6624b994631d29`,
`proxyserver/src/main/java/edu/suffolk/litlab/efsp/server/services/impl/Ecf4Filer.java`,
`submitFilingIfReady`, constructs a fresh `ReviewFilingRequestMessageType`, invokes
`reviewFiling`, and reads new FILINGID/ENVELOPEID values from its receipt. It does
not expose a correction-reference argument on this path. This is evidence for
the proxy contract, not proof of court-specific relation-back or fee treatment.
No live EFM filing is part of these tests.

`test_corrections.py` covers native and interview-originated copy/edit/payment/
submit, eligibility failures, storage loss, legacy requirements, current empty
choices, original-byte safety, remapping and stale claim protection. Its opt-in
Chromium scenarios (`CORRECTION_BROWSER_TESTS=1`) exercise filing details, keyboard
copy, mobile Review, document metadata edits, payment, explicit consent and a
stubbed successful submission. Existing handoff, detour, preview, fee and
submission tests retain coverage of retry and ambiguous outcomes.

## Validation on October 13, 2026

- Full Python suite after Claude review fixes, including both Chromium flows: 2,042 passed, 11 skipped.
- JavaScript unit suite: 90 passed.
- Native and interview-originated Chromium flows passed with synthetic court responses.
- Ruff, ty, changed-template DjLint checks, and the Docusaurus production build passed.
- ESLint passed with the unrelated local `.venv-root-owned-BROKEN/` directory excluded.
- Django's migration check reported no changes.

Screenshot evidence: [native and interview correction flows](https://gist.github.com/nonprofittechy/0df3fac6923dbcf9006c3b731ed4345f).
The gist stores PNG files with rendered Markdown image references. Capture them
with `CORRECTION_BROWSER_TESTS=1 CORRECTION_SCREENSHOT_DIR=/tmp/litefile-107-screenshots uv run pytest -q efile/tests/test_corrections.py`.

Claude Code reviewed the implementation and then reviewed the fixes. The follow-up
found no remaining actionable issues in the fixes. These include resetting the
replacement selector after upload, checking availability against the refreshed
outgoing payload, ignoring legacy requirements for removed child rows, avoiding
code lookups with missing parents, friendly replacement-ID validation, preserving
normal-draft fee refresh and consistent document ordering. Existing correction
analytics continue to count a correction as a newly started draft.
