---
id: interview-integration
title: Integration with guided interviews & Docassemble
sidebar_label: Guided interview integration
sidebar_position: 5
---

# Guided interview and Docassemble integration

A guided interview can send its generated PDFs and already-collected answers to
LITEFile. LITEFile saves a draft, resolves filing hints against current court
choices, and asks the filer for missing details. A successful transfer means
**draft created**, not **filed with the court**.

Docassemble owns the legal interview and documents. LITEFile owns court codes,
filing classifications, party types, fees, payment, submission, and clerk returns.
The Vermont `docassemble.RFApackage` interview includes a working sender.

## Configure a source

Apply the database migrations before enabling a source (`uv run python manage.py migrate`
from `efile_app/`). Migration `0023_interview_handoff` adds receipts, provenance,
and correction revisions.

Set `LITEFILE_HANDOFF_SOURCES` in the LITEFile environment to a JSON object:

```json
{
  "vermont-rfa": {
    "token": "a-long-random-secret",
    "jurisdictions": ["vermont"],
    "return_origins": ["https://interviews.example.org"]
  }
}
```

Give each source its own secret and jurisdiction allowlist. Store the secret in
server configuration, never interview text, browser JavaScript, or a URL. HTTPS
is required for return links. Source authentication is independent of the
filer's e-filing account; do not send the filer's password through this API.

Run database migrations when deploying the receiver. Configure the existing S3
upload handler with a private bucket. LITEFile accepts uploaded PDFs; it does
not fetch arbitrary document URLs supplied by an interview.

## Version 1 request

Send `POST /api/handoffs/v1/` with these headers:

```text
Authorization: Bearer <source secret>
X-LITEFile-Source: vermont-rfa
```

For documents, use `multipart/form-data`: one text field named `payload` containing
JSON and one PDF part per document, named with that document's `id`. Do not put
Docassemble expressions or unresolved variable references in the payload. The
sender evaluates only answers that are already defined, and omits unknown values.
A request without documents may instead use `application/json`.

```json
{
  "schema_version": 1,
  "jurisdiction": "vermont",
  "source_id": "opaque-stable-interview-handoff-id",
  "idempotency_key": "opaque-stable-request-id",
  "filing_intent": "relief_from_abuse",
  "case_category_name_hints": ["Family"],
  "case_type_name_hints": ["Relief from Abuse"],
  "filing_type_name_hints": ["Complaint"],
  "case": {
    "existing_case": false,
    "court_name": "Chittenden Family Division",
    "county": "Chittenden"
  },
  "filer": {
    "first_name": "Example",
    "last_name": "Filer",
    "email": "example@example.org"
  },
  "parties": [
    {
      "first_name": "Example",
      "last_name": "Filer",
      "semantic_role": "plaintiff",
      "case_side_hint": "plaintiff",
      "is_self": true,
      "is_filing_party": true
    }
  ],
  "documents": [
    {
      "id": "RFAcomplaint",
      "role": "lead",
      "form_name": "RFA Complaint",
      "sha256": "<64 lowercase hexadecimal characters from the uploaded PDF>"
    }
  ],
  "known_filing_facts": {},
  "return_url": "https://interviews.example.org/interview?session=<existing-session>"
}
```

Only `schema_version`, `jurisdiction`, `source_id`, and `idempotency_key` are
required for an empty draft. Case, filer, parties, hints, facts, and documents
may be partial or omitted. `existing_case` is a JSON boolean when known.
`case` also accepts `docket_number` and `case_title`. Existing court cases still
need a live lookup and confirmation of the case identifier.

People accept `first_name`, `middle_name`, `last_name`, `suffix`,
`organization_name`, `email`, `phone`, `address_line_1`, `address_line_2`, `city`,
`state`, `zip_code`, and a two-letter `country`. A party marked `is_self: true`
merges into the filer row, preserving collected contact details.
`is_filing_party` means the filing is made on that person's behalf. It does not
mean the person operating the browser is necessarily a party.

Documents use stable source IDs, `lead` or `supporting` roles, and SHA-256 hashes.
A nonempty bundle must contain exactly one lead. The limits are 20 PDFs, 10 MB
per PDF, 100 parties, and 512 KB of JSON metadata. Unknown source facts and numeric
suggestions remain in the receipt; numeric suggestions never populate resolved
court-code fields. Supported questionnaire answers `has_children` and
`child_count` also populate their normal filing fields.

## Response, continuation, and retries

A new receipt returns HTTP 201. An identical retry returns HTTP 200 with the same
draft ID and a fresh continuation link:

```json
{
  "draft_id": "18427",
  "state": "needs_input",
  "issues": [
    {
      "code": "court_code_required",
      "path": "court_code",
      "message": "Choose the court.",
      "view": "extraction_review"
    }
  ],
  "continue_url": "https://litefile.example.org/handoff/claim/<expiring-token>/"
}
```

The browser follows `continue_url`, signs in to its jurisdiction's account, and
explicitly claims the draft. Merely opening a link does not assign ownership.
Claim links expire after 24 hours by default; retry the same request to obtain a
fresh link. Once claimed, only the owning account can open or edit the draft.
Treat the continuation link as a private capability and avoid logging it.

A `(source, source_id)` identifies one original draft; a `(source,
idempotency_key)` identifies one request. Reusing either identity with different
content returns HTTP 409. Retry uncertain network outcomes with the **same**
payload, key, document IDs, and hashes. Do not make a new source ID on timeout.
Invalid schemas or PDF hashes return HTTP 400, bad authentication HTTP 401,
unauthorized jurisdictions HTTP 403, and unavailable document storage HTTP 503.

## Resolve and repair filing details

Claiming the draft looks up semantic hints against live court lists. The saved
answers screen also has a button to repeat that lookup after a court selection.
Only a unique name match preselects a value. Ambiguous or unmatched hints stay
editable. A code the filer has already chosen is not replaced by another guess.

State YAML can define `handoff.filing_intents`, with
`case_category_name_aliases`, `case_type_name_aliases`, `filing_type_name_aliases`,
and `documents.<source-document-id>.filing_type_name_aliases`. These curated
names supplement source hints. The Vermont configuration contains aliases for
supporting RFA forms. Court confidentiality choices remain part of filing review.

The receipt preserves original suggestions. Append-only metadata events record
live resolutions, user edits and confirmations, clerk corrections, and replacement
PDF hashes. Targeted edit links return to the missing-details list, so complete
answers do not have to be entered again. Final payment, payload validation, and
submission remain the ordinary LITEFile workflow; an empty `issues` list is not
an EFSP acceptance guarantee.

## Clerk returns and document corrections

From a locally submitted filing, choose **Correct and resubmit**. LITEFile checks
the court's current status for every filing identifier in that submission.
Only confirmed `rejected` or `returned` statuses permit a correction revision.
Pending, uncertain, partly accepted, and transport-failure outcomes cannot be
cloned automatically.

Select the fields the clerk asked to correct. The correction draft keeps the
same matter, parties, and unchanged documents. The previous submission snapshot
remains unchanged. Corrected classifications and their dependent choices are
cleared; fees must be checked again. Repeating the correction action resumes the
same revision. Filing history groups the attempts together, including returns
that occurred before a court assigned a case number.

For substantive PDF changes, use **Return to my interview to correct a PDF**.
LITEFile adds an expiring `litefile_correction` parameter to the approved return
URL. Docassemble resumes the existing interview. After the filer edits the
answers, the sender posts the updated PDFs to `/api/handoffs/v1/documents/`,
with its normal source headers and `X-LITEFile-Correction: <token>`.

The replacement request uses the original `source_id`, stable document IDs,
updated hashes, and a replacement idempotency key. It changes PDF storage
references, retains the draft's filing metadata, records the replacement, and
invalidates its fee quote. It cannot modify submitted or uncertain attempts.
Other source answers in a replacement request do not overwrite the filer's
LITEFile edits. Documents removed in LITEFile must be added there again.

## Configure the Vermont sender

In the Docassemble server configuration:

```yaml
litefile:
  enabled: true
  base_url: https://litefile.example.org
  source: court-interviews
  token: a-long-random-secret
```

This top-level configuration is shared by the Docassemble server's interviews.
Staging and production use their own credentials and endpoint. An interview can
override `litefile_config_name` in a later YAML block to select another top-level
configuration; its default is `"litefile"`. Migrate an older `litefile.rfa`
configuration by moving its contents up to `litefile`.

The RFA download screen then offers **Continue in LITEFile**. The adapter sends
the enabled court bundle, excluding the separate next-steps instructions. Its
only responsibilities are collecting known facts, hashing and transferring PDFs,
source authentication, idempotency, and presenting the continuation link.

Each adaptation includes its own `litefile.yml`, which imports the reusable
transport module. Its `data` and `data from code` blocks declare source variable
paths, party roles, semantic hints, and document mappings. The reusable helper
defaults to the normal AssemblyLine and Docassemble person attributes; an
interview can pass a custom `fields={...}` mapping when its objects differ.
The main interview only displays the included `litefile_continue_button`
template; configuration and navigation live in the adapter YAML.

Generic `litefile_*` variables and events let authors override defaults with
later data or code blocks. The shared `litefile_send` event prepares and saves
the AssemblyLine cache, then uses Docassemble's `BackgroundAction` for the
network upload. Its first wait response persists the cache before the worker
reads it. An initial routing block consumes the result before the host
interview's mandatory blocks run. The worker reads credentials from the
selected server configuration, while the background task arguments remain
empty.

The Python helper has no interview-specific paths or classifications. It uses
AssemblyLine's `get_cacheable_documents()` and retains that cache with the
transfer payload, so retries reuse file handles and hashes without making
separate frozen PDF copies. A new correction token starts a new cache.


For isolated local testing, both source configurations can explicitly set
`allow_insecure_local_development: true`. The receiver also requires Django
`DEBUG=True`; production return links still require HTTPS. Use synthetic answers
and the dev EFSP, and keep local testing credentials outside version control.

## Retain and expire unclaimed data

A draft exists before the filer claims it, so unclaimed data needs a retention
schedule. Preview expired handoffs with:

```bash
uv run python manage.py expire_unclaimed_handoffs --days 7
```

Add `--apply` to delete those unclaimed receipts, drafts, and private PDFs.
Claimed drafts and submission revisions are unaffected. Schedule this command
according to the deployment's retention policy; also configure access-log
redaction for capability URLs and a storage lifecycle for failed-upload orphans.
