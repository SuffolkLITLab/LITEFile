# Filing draft data model foundation

This PR introduces the durable filing aggregate that future filing-flow PRs can migrate toward.

## New source-of-truth models

- `FilingDraft`: one filing workflow instance. It owns jurisdiction, status, current workflow step, case classification, existing-case identifiers, selected payment account, extracted guesses, temporary extra case data, and submission response.
- `FilingDocument`: one uploaded lead or supporting document. It owns S3/public URL metadata, file metadata, filing/document/component codes and names, courtesy copy email, and document order.
- `FilingParty`: one party/person associated with the draft. It owns role, party type, contact, name, and address fields.

The model intentionally keeps `extra_case_data` and document/party `metadata` JSON fields as temporary escape hatches so the UI can move off session blobs incrementally without blocking on a perfect schema.

## Backwards-compatible bridge

The existing session-backed flow still works. This PR adds service helpers that can shadow-write the current session shapes into the durable models:

- `create_draft()`
- `ensure_draft()`
- `update_draft_from_case_data()`
- `sync_documents_from_upload_data()`
- `draft_snapshot()`

The options/start flow now creates a `FilingDraft` through `POST /jurisdiction/<jurisdiction>/drafts/` and redirects to the workflow's first document-upload step. The old session start path remains as a browser fallback.

## Future migration sequence

This is intended as the foundation for follow-up PRs:

1. Update the remaining case-data save APIs to use `update_draft_from_case_data()`.
2. Update upload APIs to use `sync_documents_from_upload_data()`.
3. Move payment selection into explicit draft fields.
4. Render review from `FilingDraft`, `FilingDocument`, and `FilingParty`.
5. Move final submission to a draft-backed submission service.
6. Remove legacy arbitrary session-merge APIs and localStorage/sessionStorage persistence.
