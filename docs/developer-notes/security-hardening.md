# Security and extraction hardening

This work keeps YAML authoring and the existing per-process configuration cache. It addresses the highest-priority findings from the review of `f3b1d17`.

## Changes

- Remove the public legacy S3 upload, mock upload, bucket diagnostic, and session-debug routes in every environment. Normal uploads continue through the authenticated draft workflow.
- Remove submission headers, payloads, response bodies, and filing-history session tokens from application logs. Default application logging to INFO, including production.
- Upgrade Django to 5.2.17 and update the resolved packages flagged by the dependency audit. CI installs the locked dependencies and runs `pip-audit`, including the PDF-processing dependencies. The editable application and the two unpublished GitHub court-directory packages are outside this audit's coverage.
- Restrict jurisdiction lookup to the canonical names of installed, non-symlink YAML files. Unknown names and path aliases fail before file access or cache insertion. Restart processes when adding or removing jurisdiction files. Generic public pages use no jurisdiction configuration until a state is selected.
- Give each extraction attempt a unique claim token and renewable lease. Requeued or reclaimed work invalidates earlier results, failures, and heartbeats. Recover expired final attempts to a terminal failure and apply bounded exponential retry backoff.
- Run each extraction in a separate Linux process with a wall-clock alarm and address-space limit. The supervisor renews the lease every 30 seconds while the child runs, terminates obsolete or timed-out children, and records interrupted attempts without persisting exception contents.
- Recheck the AI preference and claim before analysis and before the evidence and classification stages. Results from an obsolete attempt cannot update the draft. A preference change cannot retract data already sent or an upstream request already in flight.
- Disable persistent database connections in ASGI deployment settings, configure WhiteNoise through `STORAGES`, and remove the bucket-listing request from ordinary S3 client initialization. S3 calls now have explicit connection/read timeouts and bounded retries.

## Deployment

Stop old extraction workers before applying migration `0028_extraction_claim_leases` and starting the new web and worker image. Old worker code does not honor claim tokens; mixing worker versions defeats the protection. Existing pending jobs remain eligible. Interrupted processing jobs without a lease become recoverable after the existing 15-minute stale interval.

`DOCUMENT_EXTRACTION_TIMEOUT_SECONDS` defaults to 600. `DOCUMENT_EXTRACTION_MEMORY_MB` defaults to 768 and limits virtual address space, not just resident memory. Numerical libraries use one thread in each child. Leave memory for the supervisor and operating system when setting container limits. Validate these bounds with representative documents before increasing replica counts; they are safety bounds, not measured capacity recommendations. The deployed worker must support Linux `resource` limits and `SIGALRM`.

Each worker supervisor processes one job at a time. Size workers using measured queue wait, processing duration, peak memory, database connections, and upstream quotas. No deployment replica count or connection pool has been changed here.

Rebuild the image so `uv sync --frozen` installs the new lockfile and `collectstatic` produces hashed and compressed assets. Verify production response headers after deployment. Review retained logs and rotate or revoke credentials confirmed to have been recorded; source changes cannot remove historical disclosures.

## Follow-up work

- Aggregate upload limits and storage quotas, actual file-content validation, durable upload staging, and orphan cleanup.
- Restore CSRF checks on browser session mutation and submission endpoints, with matching JavaScript changes and CSRF-enforcing tests.
- Stop unnecessary session writes on polling; test expiry behavior before changing the global session setting.
- Measure web workflows and extraction recovery under realistic load, including PostgreSQL contention, upstream rate limits, and difficult PDFs. Unit interleaving tests do not establish production throughput.
- Validate and version compiled YAML configurations; add derived-response caching only where profiling shows a benefit.

The submission claim and ambiguous-outcome safeguards are unchanged. Extraction retries must not be reused as an automatic court-submission retry mechanism.
