# Filing updates contract

This note records the verified contract for LITEFile filing emails and the upstream EFSPProxy. It is an implementation and release checklist, not evidence of partner approval or production delivery.

## Email ownership and contract

LITEFile does not send the filing notifications directly. It selects server-owned, jurisdiction-configured subject and body text, then includes those fields in the filing request. EFSPProxy sends the submission confirmation and later callback messages. Tyler may also send its own messages, including account activation. The Illinois partner issue asks that LITEFile-configured notices continue alongside Tyler messages, use an Illinois-branded sender domain, and have jurisdiction-specific subject/body text. It also calls out Tyler Odyssey activation mail as a separate, earlier message that needs an explanation during onboarding. See [LITEFile #157](https://github.com/SuffolkLITLab/LITEFile/issues/157).

The upstream JSON contract in `docassemble-EFSPIntegration/efm_client.py` forwards these per-filing template fields:

| Event | Payload fields |
| --- | --- |
| Submission confirmation | `email_confirmation_subject`, `email_confirmation_contents` |
| Accepted status | `acceptance_subject`, `acceptance_contents` |
| Rejected status | `rejected_subject`, `rejected_contents` |
| Other status | `neutral_subject`, `neutral_contents` |

The proxy sends one confirmation for a submitted envelope. Its `transaction_id` template value joins the envelope's transaction IDs, and the confirmation also receives `envelope_id`. A later callback is handled for an individual filing transaction and its template variables include that transaction ID. The callback context has no `filing_id` field, so callback email copy must not assume it can link directly to one filing by ID. LITEFile's configured tracker URL points to the local submission reference; when that submission contains multiple filing IDs, the tracker asks the filer to choose which filing to view. The current copy's wording “A filing in your submission” reflects that individual filings in one submission can reach different outcomes.

EFSPProxy renders the callback status templates with `name`, `court_name`, `case_type`, `case_title`, `status`, `message_text`, `transaction_id`, and `message_url` when the callback supplies a nonblank URL. Its confirmation template also has `envelope_id`; it uses the same name, court, case type, title, and transaction ID values. EFSPProxy renders templates as plain text. Its REST guide describes the template fields and variables; implementation is in `OrgMessageSender.java`.

For upstream confirmation, the proxy chooses `users[0].email` when `users[0]` is marked as the form filler and has an email. Otherwise it chooses `lead_contact.email`, which is required when the form-filler is not among the users. The Docassemble client serializes both fields when present. For a later court callback, the recipient is the email stored on the proxy transaction at filing time. The sender is the proxy server's configured `fromEmail`; when unset, the current proxy source falls back to `massaccess@suffolk.edu`. Transport uses `EMAIL_METHOD` and either SendGrid (`SENDGRID_API_KEY`) or SMTP settings. Do not treat the legacy default as the approved Illinois sender.

Upstream callback statuses are `ACCEPTED`, `REJECTED`, or neutral/other. `UpdateMessageStatus.fromStr` maps the raw status strings `accepted` and `rejected` to the first two categories; `returned` and unknown strings map to neutral. The template variable named `status` is separate: the callback fills it with the court's configured status display name when available, otherwise the raw status code or status text. When the court config has `showreturnonreject`, the callback's `message_text` says “returned” while its category remains `REJECTED`. As a result, the rejection template is used for that configured rejection, but a literal `returned` status code selects the neutral template. Do not assume a template conditional can infer the category from `status` in every court configuration.

## Delivery and duplicate behavior

The upstream sender considers HTTP-style results 200, 202, and 204 successful; it returns false for other results, an invalid/missing recipient, or a caught `IOException`. The callback logs a failed send and still returns an OK callback receipt. Filing submission similarly invokes `sendConfirmation` without acting on its boolean result. The inspected callback and submission paths do not provide an idempotency guard around notification sends. A repeated status callback can therefore send another email, while a failed email does not make the callback retry guarantee visible to the caller. These are observations of the proxy code; no delivery was attempted during this review.

## Related work and release gates

- [LITEFile #297](https://github.com/SuffolkLITLab/LITEFile/issues/297) requests customizable submission, acceptance, and rejection messages, including tracker link, next steps, and local court/help contacts. The existing upstream contract carries templates and basic filing/court status values; it does not itself prove those jurisdiction-specific contents are configured or approved.
- [LITEFile #229](https://github.com/SuffolkLITLab/LITEFile/issues/229) defines the filing detail tracker and its status presentation. Keep email status language aligned with the tracker and concise: state what happened, what the filer needs to do, and only context needed to act. Do not repeat status banners or include inapplicable guidance.
- [EfileProxyServer #375](https://github.com/SuffolkLITLab/EfileProxyServer/issues/375) tracks per-server SendGrid API credentials. The issue remains open in the inspected GitHub state. Discussion rejects storing API keys directly in the database and considers secret storage. It does not establish that per-jurisdiction sender domains or credentials are implemented.

The filing detail page presents `STATUS_PRESENTATION` labels and a tracker derived from the existing filing status. Its normal path is Sent → Received → Clerk review, followed by the actual outcome. `submitting` maps to Sent; `submitted` and `receipted` map to Received; `under-review` and `reviewed` map to Clerk review; `accepted` ends at Accepted; `rejected` and `returned` end at Returned for changes. `failed` and `cancelled` stop progress, `served` is presented separately, and unknown statuses use a neutral message. See `efile/services/filings.py` (`STATUS_PRESENTATION`, `TRACKER_STAGES`, and `filing_tracker`). Email links should land on the submission tracker and let a filer select among multiple filings when needed.

Before release, verify the following with configuration and an end-to-end delivery check:

1. Decide which channel handles each event so LITEFile-configured proxy messages and Tyler messages do not duplicate or contradict one another. Keep Tyler account activation mail identified separately.
2. Confirm jurisdiction-specific sender name/address/domain, provider credentials, and email authentication with the partner/operations owner. No partner approval or production sender configuration is evidenced by the code/issues reviewed here.
3. Confirm the configured short copy for submission, accepted, rejected, and neutral statuses. Account for the upstream mapping where a literal `returned` status selects the neutral template, and where `showreturnonreject` only changes callback message text. Each email should plainly state the event, the filer action (if any), and the minimum useful context. Do not claim an action is required when none is.
4. Exercise successful delivery, invalid/missing recipients, provider errors, duplicate callbacks, and retries. Confirm what the filer and support staff see when sending fails.
5. Verify the tracker URL uses the correct submission reference and that the destination gives the filer the detail and correction path described by the status email.
6. Confirm final filing-detail access remains authorized. LITEFile now checks ownership when a detail ID is present in another local draft, while remote-only filing history remains protected by the user's Tyler token. The proxy passes that user's credentials to Tyler for the requested filing ID and has no separate filing-owner lookup. Verify Tyler enforces record access for that credential, and preserve access to legitimate history entries that have no local `FilingDraft`.

## Indexed filing ownership

Migration `0044_filing_identifiers` creates searchable filing identifiers and backfills saved submission responses in bounded batches. Apply this migration before serving the updated filing-detail view. Both local-submission lookup and cross-account authorization use the filing-ID index; remote-only lookups do not load other accounts’ draft responses or snapshots.

`FilingDraft.save()` updates these identifiers atomically when saving `submission_response`. Code that changes this response must use `save()` rather than `QuerySet.update()` or bulk writes. This table stores identifiers only; filing status still comes from the proxy.

Correction links use a normalized returned/rejected status, including mixed-case and whitespace-padded values. Failed filings remain ineligible. The review regression tests cover response-index updates, historical backfill, normalized correction links, and remote-only lookups without materializing other accounts’ drafts; all 49 targeted checks passed.

## Evidence reviewed

- Local `docassemble-EFSPIntegration/docassemble/EFSPIntegration/efm_client.py` whitelist and lead-contact serialization.
- `EfileProxyServer/docs/rest_guide.md`, `OrgMessageSender.java`, `SendMessage.java`, `FilingReviewService.java`, and the Tyler callback implementation from the local EfileProxyServer checkout.
- Local `FilingInformationDocassembleJacksonDeserializer.java`: when `users[0]` is marked form filler and has email, that person's email takes precedence. Otherwise the proxy uses `lead_contact`, whose email it requires. The Docassemble client serializes both `users` and `lead_contact` when present.
- Local `FilingReviewService.getFilingDetails`: requires proxy authorization, obtains the authenticated `TylerUser`, and passes that user's credentials to the EFM detail request. No separate filing-owner check is present in the inspected proxy method.
- The repository proxy rendering harness is in `efile_app/tests/notification-proxy-contract/`. It uses the proxy's real Jinjava and callback status enum from the supplied proxy JAR. It checks that bodies render while subject fields remain unchanged, since upstream sends the subject directly to the mail provider. A synthetic `{{ status }}` subject probe is preserved literally while an equivalent body probe is rendered. It does not call any provider.

To run the harness, use the `efspserver-with-deps.jar` from an EfileProxyServer build and pass its location through `EFSP_PROXY_JAR`. Run these commands from `efile_app/`:

```sh
export EFSP_PROXY_JAR=/path/to/EfileProxyServer/proxyserver/target/efspserver-with-deps.jar
proxy_contract_dir="$(mktemp -d)"
UV_CACHE_DIR="${TMPDIR:-/tmp}/litefile-uv-cache" uv run python tests/notification-proxy-contract/generate_payload.py --output "$proxy_contract_dir/input.json"
java -cp "$EFSP_PROXY_JAR" tests/notification-proxy-contract/RenderContract.java --input "$proxy_contract_dir/input.json" --output "$proxy_contract_dir/report.json"
```

The harness was exercised with OpenJDK 21.0.12.1 and the existing local `EfileProxyServer/proxyserver/target/efspserver-with-deps.jar`; the JAR was not rebuilt because Maven and javac are unavailable.

| Check | Result |
| --- | --- |
| Full backend regression suite (`uv run pytest -q`) | 1,841 passed; 4 skipped |
| Notification Django tests | 11 passed |
| Sprint focused checks | 51 passed |
| Integrated browser check | Passed |
| Proxy Jinjava contract harness | Passed with existing proxy JAR; no email provider called |
| End-to-end email delivery | Not performed |

Repository-wide Ruff and `ty check` passed. The new tracker stylesheet passed Stylelint, and `git diff --check` passed.
- GitHub issues #297, #229, #157, and EfileProxyServer #375, read on 2026-10-11.
