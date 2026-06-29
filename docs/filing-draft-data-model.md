# Filing draft data model foundation

This PR introduces the durable filing aggregate that future filing-flow PRs can migrate toward.

## New source-of-truth models

- `FilingDraft`: one filing workflow instance. It owns jurisdiction, status, current workflow step, case classification, existing-case identifiers, selected payment account, extracted guesses, temporary extra case data, and submission response.
- `FilingDocument`: one uploaded lead or supporting document. It owns S3/public URL metadata, file metadata, filing/document/component codes and names, courtesy copy email, and document order.
- `FilingParty`: one party/person associated with the draft. It owns role, party type, contact, name, and address fields.

The model intentionally keeps `extra_case_data` and document/party `metadata` JSON fields as temporary escape hatches so the UI can move off session blobs incrementally without blocking on a perfect schema.

## Service boundaries

The durable draft code is split into three layers:

- `services/drafts.py` contains request-independent operations on durable models.
- `services/current_drafts.py` resolves the current browser's draft while enforcing ownership and jurisdiction. The session contains only the current draft ID; it is not a state store.
- `services/legacy_draft_bridge.py` is the temporary compatibility adapter that translates the old `case_data` and `upload_data` blobs. Only legacy session endpoints import it, so it can be removed without changing the durable service.

The options/start flow creates a `FilingDraft` through `POST /jurisdiction/<jurisdiction>/drafts/` and redirects to the workflow's first document-upload step. The old session start path remains as a browser fallback. While that flow remains, its actual case and upload save endpoints shadow-write through the compatibility adapter.

Drafts require an authenticated owner. Every current-draft lookup verifies that owner, active status, and, when known, jurisdiction before returning the object.

## Migration rollout

`efile` previously had no migrations even though existing environments may already have the `UserProfile` table. Migration `0001` therefore contains only that baseline model, and migration `0002` creates the new filing tables. Existing environments must run `migrate --fake-initial`; the Fly release command includes that option. Fresh databases apply both migrations normally.

## Future migration sequence

This is intended as the foundation for follow-up PRs:

1. Replace legacy case-data endpoints with typed draft updates.
2. Replace legacy upload endpoints with typed document updates.
3. Move payment selection into explicit draft fields.
4. Render review from `FilingDraft`, `FilingDocument`, and `FilingParty`.
5. Move final submission to a draft-backed submission service.
6. Remove `legacy_draft_bridge.py`, arbitrary session-merge APIs, and browser storage persistence.
