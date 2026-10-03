# Staff privacy requests and aggregate usage

This runbook accompanies issue #162. The staff area uses Django admin with
purpose-built lookup, privacy-request, and reporting views. It is not linked
from public pages. Set `LITEFILE_STAFF_PATH` to a private URL segment and share
that URL through the staff onboarding channel. The URL is not an authentication
secret: local passwords, TOTP, and jurisdiction-scoped roles enforce access.

## Deployment and onboarding

Install the locked dependencies and run `uv run python manage.py migrate`
before enabling collection. Existing object ownership is inventoried by the
migration; it does not backfill usage statistics or contact S3.

### Bootstrap from environment variables

From a trusted deployment console, supply the following through shell variables,
your password manager, or deployment secrets. There are no default credentials.
Global environment variables take precedence over the development `.env` file.

| Variable | Purpose |
| --- | --- |
| `LITEFILE_STAFF_BOOTSTRAP_USERNAME` | Required initial superuser name |
| `LITEFILE_STAFF_BOOTSTRAP_PASSWORD` | Required unique password that passes Django password validation |
| `LITEFILE_STAFF_BOOTSTRAP_EMAIL` | Optional staff contact email |
| `LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET` | Optional Base32 secret containing 20–40 random bytes; otherwise generated |

With those variables set, run:

```bash
cd efile_app
uv run python manage.py migrate
uv run python manage.py bootstrap_staff
```

Bootstrap creates an active local superuser and a confirmed TOTP device together.
If no TOTP secret was supplied, it prints the newly generated setup URI once.
If a secret was supplied, it does not print the credentials. Repeating the command
leaves existing credentials and roles unchanged; it refuses to promote a normal
account or overwrite an account without a working TOTP device. It never runs
automatically at server startup. Remove bootstrap credential variables from the
runtime environment after setup; they are not needed to sign in or run the app.

For a Bash setup without putting a password in command history:

```bash
export LITEFILE_STAFF_BOOTSTRAP_USERNAME="your-admin-name"
read -r -s -p "Unique administrator password: " LITEFILE_STAFF_BOOTSTRAP_PASSWORD
echo
export LITEFILE_STAFF_BOOTSTRAP_PASSWORD
uv run python manage.py bootstrap_staff
unset LITEFILE_STAFF_BOOTSTRAP_PASSWORD LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET
```

The alternative interactive setup remains available:

```bash
cd efile_app
uv run python manage.py createsuperuser
uv run python manage.py provision_staff_totp STAFF_USERNAME
```

The second command prints an `otpauth://` secret. Import it into an authenticator
using its manual setup/import feature. Treat the console output as a credential;
do not save it in logs, tickets, screenshots, or shared shell transcripts. Staff
sign in with a local password and a fresh TOTP code. Court authentication is
never called by the staff sign-in form. Password failures are limited to ten per
username in fifteen minutes; TOTP has its own throttle and replay prevention.
Staff sessions require reauthentication after fifteen minutes, including
superusers. Staff identities cannot be used for ordinary filer workflows.

The superuser can create staff accounts in the private admin site, provision
their authenticator from the account's TOTP setup link, and grant one or both
roles independently for each configured jurisdiction:

| Role | Access |
| --- | --- |
| Account management | Minimal account/draft lookup, session revocation, verified privacy requests |
| Aggregate reporting | Suppressed reports and, when enabled, CSV exports |
| Superuser | Both roles across configured jurisdictions and staff provisioning |

`is_staff` alone gives no access. Analysts cannot open account/request pages or
grant roles. Account managers cannot export reports without the reporting role.
Role revocation and account deactivation take effect on the next request.
No ordinary litigant model is registered for unrestricted admin editing.

For recovery, verify the administrator through the staff recovery procedure,
then use `provision_staff_totp STAFF_USERNAME --reset` from the deployment console.
This replaces the device and revokes that staff account's sessions. There are no
password-only or static-token recovery routes in the backend. Protect deployment
console access, database credentials, and TOTP secrets stored in the database.
Use the existing production HTTPS, secure-cookie, and HSTS settings. Ensure the
backend and database have encryption at rest and restricted operator access.

### Local demo

Use the development settings with the local SQLite database. After migrations
and staff bootstrap, create synthetic lookup and report fixtures:

```bash
cd efile_app
uv run python manage.py seed_staff_demo
LITEFILE_ANALYTICS_EXPORT_ENABLED=true \
LITEFILE_PRIVACY_DELETION_ENABLED=true \
uv run python manage.py runserver 127.0.0.1:8001
```

Open <http://127.0.0.1:8001/staff-7c83f0a2/> when using the default
`LITEFILE_STAFF_PATH`. Sign in with your bootstrapped local administrator password
and the six-digit TOTP from your password manager. Store the **setup secret** or
the `otpauth://` URI; a displayed six-digit code expires after thirty seconds.
Port 8001 keeps this local demo separate from a filing app already using port
8000. Use SHA-1, six digits, and a thirty-second period. If you change
`LITEFILE_STAFF_PATH`, use that segment in the URL instead.

Staff pages use `Referrer-Policy: same-origin`: browser forms retain the origin
needed for Django's CSRF checks, while requests to other origins omit referrer
information. Do not use `no-referrer` for these pages or trust the literal
`null` origin; native form submissions under that policy can fail CSRF checks.
After changing this header, restart the server and reload the login page before
submitting it. See [the browser behavior documented by MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy#effect_on_the_origin_header).

The seed command creates five synthetic filers and ten drafts per configured
jurisdiction, plus started/review aggregates for the previous complete UTC month.
It prints the report dates. In Account lookup, search for
`litefile-demo-illinois-1@example.invalid` in Illinois, or the corresponding
configured jurisdiction. In Aggregate usage, select that jurisdiction and the
printed dates, monthly grouping, and Total; each new/existing cell has five
contributing demo accounts. Repeated runs preserve existing fixtures and counts.
Demo users have unusable passwords and are excluded from ordinary collection.
No documents are uploaded and no court accounts or filings are created.

Demo seeding refuses deployed hosts, non-debug settings, and non-SQLite databases.
Normal collection remains disabled under development settings; the seed command
explicitly creates synthetic aggregates for testing. The command above enables
CSV exports and verified deletion in the local demo. Deleting synthetic accounts
removes their local operational data while the anonymous counters remain.
Keep production credentials and data out of this demo database.

## Enablement and policy decisions

The following environment switches default to `false`:

```text
LITEFILE_ANALYTICS_ENABLED=true
LITEFILE_ANALYTICS_EXPORT_ENABLED=true
LITEFILE_PRIVACY_DELETION_ENABLED=true
```

Collection also excludes `DEBUG` deployments, stand-in-document deployments,
staff accounts, and designated test accounts. Before a production test, mark its
local account with `uv run python manage.py exclude_analytics_account ACCOUNT_ID`.
This excludes future events; it cannot subtract already anonymous aggregates.

Wait until every web and worker instance runs the new code before enabling
deletion. Older instances do not enforce the freeze checks. Finish or stop old
workers during rollout; do not enable destructive actions during a mixed-version
deployment.

Before enabling deletion or exports, the service owner must approve verification
and response procedures, retention exceptions, backup handling, allowed report
dimensions, and disclosure thresholds. The conservative implementation floor is
five distinct contributing local accounts per cell; increase it with
`LITEFILE_ANALYTICS_MIN_CONTRIBUTORS`. This is a disclosure safeguard, not a legal
determination or a guarantee against identification using outside information.

Choose `LITEFILE_STAFF_REQUEST_RETENTION_DAYS` (default 90) for resolved request
and audit records. Open work and outstanding backup/provider dispositions are
not automatically pruned. Review aging open requests instead of discarding
their restricted manifests. No general operational-retention expiry is added
by this feature; retain the existing service policy until a separate retention
decision changes it.

## Verify and process a request

1. Receive the request at the jurisdiction's existing contact address. Verify
   identity and authority using an approved contact-channel procedure. Never
   ask for passwords or copies of court filings as identity evidence. Keep
   intake correspondence in the approved support system, not in free-text
   fields in this backend.
2. Find the explicit local account by ID, email plus jurisdiction, or draft ID.
   Matching emails across jurisdictions are separate accounts and separate
   approvals. The lookup shows metadata and counts, without document contents,
   payment information, session credentials, or raw session payloads.
3. Record either selected owned drafts or all LITEFile-held data for this local
   account. Staff accounts are excluded. Disputed ownership, another person's
   records, and unclaimed handoffs require manual review; do not infer ownership
   from names, document text, or a matching email.
   Select **Review deletion** to save the scope and open its inventory preview.
   This step creates a deletion request; deletion takes place after the final
   confirmation. Existing pending requests can be reopened through
   **Continue deletion review** on the account page or **Deletion requests**
   on the staff home page.
4. Confirm the identity/authority checkbox and select **Verify and continue**.
   Review the counts and blockers, then type the request reference and select
   **Permanently delete account** or **Permanently delete selected filings**.
   Failed attempts provide **Retry deletion** after blockers are resolved.
   A signed, expiring
   preview prevents confirmation of a changed inventory without another review.
   GET requests never verify, revoke sessions, provision TOTP, or delete data.
5. Reconcile `submitting`/`error` filings with the filing service before deletion.
   An uncertain timeout is not a confirmed failure. Stop or finish active
   extraction workers. Shared objects and correction chains outside scope block
   automatic deletion; expand the scope only with verified authority, or record
   an approved operator disposition outside this workflow.
6. Processing freezes the affected drafts and revokes affected browser sessions.
   Uploads, party edits, extraction claims, and stale model saves cannot restore
   frozen or erased drafts. Account-wide requests revoke every stored session
   for that account. Selected-draft requests revoke sessions pointing to those
   drafts and legacy sessions holding copied filing data.
   Filing operations for the account pause while cleanup is incomplete; unrelated
   stored drafts and plans remain intact and become usable again after completion.
7. Both original and prepared S3 objects, prior owned copies, versions, and delete
   markers are erased. The restricted manifest records object progress before
   database deletion. A failed object leaves the request in needs attention,
   with frozen records and retry information intact. Missing objects are safe to
   retry. No partial attempt is reported as complete.
8. Successful cleanup removes the scoped database records, clears target IDs and
   object keys from the request, and keeps only counts, staff attribution, dates,
   the random request reference, and the outcome. Aggregate counters remain.

The request page distinguishes **live-system deletion completed** from unresolved
backup/provider work. Mark the external disposition resolved only after the
approved backup expiry/isolation and provider disposition are confirmed. If an
exception applies, refer it to the person authorized to approve exceptions;
do not mark it resolved merely to close the queue.

Suggested response: “We deleted the specified copies held in LITEFile's active
systems. This does not withdraw a court filing or delete court or Tyler records.
[Describe the actual backup/provider disposition and any remaining exception.]
Anonymous aggregate usage counts remain.” Do not tell a user that all copies
everywhere were erased while required work remains outstanding.

## Data inventory and boundaries

| Store | Automated scope and retention |
| --- | --- |
| Local profile/preferences | Removed on account-wide deletion; excludes staff accounts |
| Plans and archived-case metadata | Removed with the selected local account; preserved for draft-only requests |
| Drafts and corrections | Removed only within the verified scope; external correction relationships block removal |
| Parties, submission snapshots/responses | Cascade with scoped drafts |
| Extractions, evidence, provenance, handoff receipts/replacements | Cascade with scoped drafts |
| Pending activations | Matching account email in the selected jurisdiction only |
| Database sessions and session-held court tokens | Revoked by account or affected-draft scope; no payloads shown to staff |
| S3 current/original/prior objects | Exact owned keys erased, including versions and markers; outside-scope references block deletion |
| Upload ownership inventory | Operational only; outlives removed document rows, cascades with the erased draft |
| Usage outbox, contributor and matter deduplication | Operational only; event dimensions clear after rollup, outbox drains before erasure, account links cascade on account deletion |
| Aggregate counters | Retained indefinitely without account/session/draft IDs or lookup hashes |
| Request manifests | Restricted and retained while cleanup is unfinished; cleared after successful live-system cleanup |
| Request/audit history | Minimal counts/outcomes; pruned after configured retention when external disposition is resolved |
| Login throttles | Keyed hashes, no raw usernames/IPs; pruned after one day by the usage worker |

Extraction workers use temporary directories with context-managed cleanup.
Deletion defers while processing is active. After a crashed worker, confirm the
process stopped and clear its abandoned temporary directory through the existing
operator procedure before retrying. This workflow does not scan arbitrary host
directories or claim to erase provider caches. Application configuration caches
contain court configuration, not filer documents. Pre-feature orphan uploads,
failed rollback cleanup without a durable owner, host crash residue, old logs,
backups, and external-provider copies require operator inventory/disposition.

Application staff audits and new storage/authentication logs omit payloads,
filenames, tokens, and lookup emails. Lookup terms use POST and short-lived staff
sessions. Configure proxy/access/error-monitoring logs to omit staff request
bodies, query strings, account locators, authenticator provisioning responses,
and cookies. Apply the approved log retention policy to older logs.

S3 IAM must permit `GetBucketVersioning`, `ListBucketVersions`, `DeleteObject`,
and `DeleteObjectVersion` for the application's private storage. Object lock,
MFA deletion requirements, or denied version access fail closed and need operator
resolution. A delete marker alone is not permanent erasure; see
[AWS's version deletion documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html).
Shared keys are retained as blockers, including keys inventoried from earlier
application-authored submission snapshots. The tool never silently deletes an
outside-scope copy to satisfy a request.

Backups need a documented expiry or approved isolation policy and a restore
procedure. After a restore, keep the application offline and reapply the verified
deletion ledger/support dispositions before making restored accounts or uploads
available. Do not simply restore an old database and resume service: its deleted
accounts and S3 references could become live again. Court filings, Tyler
accounts, and AI-provider retention require their own disposition; there is no
automatic provider deletion integration in this MVP.

## Reporting definitions

Events record their UTC date, configured jurisdiction, and new/existing/unknown
category at the time they occur. Historical counts are not rewritten when the
filer changes an answer.

| Metric | Counting rule |
| --- | --- |
| `started` | Once per created owned draft or first handoff claim; unclaimed handoffs excluded |
| `review` | Once per draft reaching the validated review screen |
| `submission_attempt` | Once per claimed logical operation; duplicate clicks/transport retries are not additional attempts |
| `transmitted` | Once per draft with confirmed delivery to the filing service; not court acceptance |
| `submission_error` | Once per logical operation with a confirmed pre-call failure or API rejection; ambiguous outcomes excluded |
| `document_uploaded` | Once per document row; includes preparation outcome and original PDF form-field presence |
| `matter_first_used` | First confirmed transmission into a known matter for this local account |

Detailed monthly marginals cover configured case type, filer side, self versus
someone else, five-digit filer ZIP, preparation outcome, original PDF form-field
presence, and a first/2–5/6+ transmission frequency band. They are independent
breakdowns, not a row combining ZIP with case details. Unknown answers stay
unknown. `no_form_fields` includes both ordinary PDFs and PDFs already flattened;
it is not a claim that every unchanged upload was previously flattened. Word
files and legacy unknowns are separate from tested PDF input.

Case types use deployment-owned configuration keys; unfamiliar court types are
`other_or_unknown`. Extend configured matches to make those reports more useful.
Matter identity follows a plan or a known court/case identifier, with a draft
fallback when neither exists. Matters are per local account, not unique cases
across all people or a count of unique human filers. Deduplication records are
operational data, not anonymous analytics. No user-level export is offered.

The outbox and counters update atomically with database uniqueness constraints.
Worker retries do not double-count. A queue failure logs a fixed collection
degradation message without stopping the filing; alert on that message and worker
failures. The dashboard shows retained coverage, freshness, and pending work.
Coverage starts at deployment; there is no usage backfill. Counters survive
session expiry, restarts, and contributing account deletion.

Daily core reports and full-calendar-month reports use fixed UTC buckets.
Detailed reports require full calendar months. If any cell in the requested
breakdown has fewer than the configured contributor threshold, that whole
breakdown/period is suppressed, including its subtotals and rare labels. No partial
detailed breakdown can be subtracted from a core total. Dashboard and CSV share
the same service.
No arbitrary combined demographic breakdowns, free text, names, document text,
case numbers, IP addresses, credentials, or persistent tracking IDs are stored
in the permanent counters. Contribution thresholds count local accounts, not
unique people. Review the disclosure policy before sharing reports externally.

## Workers, monitoring, and rollback

Schedule these commands using the deployment's existing scheduler:

The existing extraction supervisor in `fly.toml` and `compose.yml` also runs
usage rollups once a minute, including while a PDF child is running. It catches
analytics failures independently so extraction continues. An additional usage
worker is optional; concurrent rollups are idempotent. The standalone command
is useful for draining a backlog and for deployments without that supervisor.

```bash
uv run python manage.py process_usage_events              # every minute; batches of 1,000
uv run python manage.py process_privacy_requests            # preview interrupted confirmed work
uv run python manage.py process_privacy_requests --apply    # retry confirmed work after reviewing failures
uv run python manage.py prune_staff_requests                # daily
uv run python manage.py clearsessions                       # existing session expiry housekeeping
```

The retry command only resumes previously confirmed processing or storage failures;
it never verifies or automatically starts a newly received/verified request. It
uses the original responsible operator's current role grants. Revoked permission
requires operator reassignment/review instead of bypassing access control.

Alert on growing outbox backlog, stale freshness, collection degradation logs,
interrupted processing, storage failures, and old unresolved external dispositions.
Use a staging fixture with original/prepared/versioned/shared uploads to validate
IAM, local TOTP onboarding, reports, and worker restarts before enabling production
switches. Automated tests use mocked storage and never submit live filings.

To disable collection, export, or deletion, set its switch to `false` and restart
the application and workers. Keep existing counters and open manifests. Do not
unfreeze drafts or discard manifests after partial erasure. Turning a switch off
cannot restore already erased objects. Existing migration/schema must remain while
these code paths are deployed; rollback code and worker configuration together.
The authentication implementation uses
[django-otp's TOTP/admin integration](https://django-otp-official.readthedocs.io/en/stable/auth.html).
