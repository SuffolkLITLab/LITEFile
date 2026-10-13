---
id: filing-code-operations
title: Operate filing-code synchronization and search
sidebar_label: Filing-code operations
---

# Operate filing-code synchronization and search

This checklist consolidates the existing [deployment instructions](./deployment.md#filing-code-search-index)
and [storage decision note](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/filing-code-search-storage.md).
It describes the October 13, 2026 implementation. Assign a code-sync operator,
backup operator and court/proxy escalation contact in the
[maintenance register](../partners-courts/maintenance.md) before relying on a
review schedule.

## Establish the environment and schedule

| Setting | Meaning / check |
| --- | --- |
| `EFSP_URL` | Target proxy environment. Confirm test versus production; never mix their codes |
| `FILING_CODE_SYNC_MODE` | `database` is the default read-only code-table copy; `bulk` uses the proxy HTTP catalog; `legacy` crawls list APIs |
| `EFSP_CODES_DATABASE_URL` | Least-privilege code reader for database mode. Supply through deployment secrets; omit credentials from evidence |
| `FILING_CODE_SYNC_TIME` | Daily local `HH:MM`, default `04:30`; choose after the upstream refresh |
| `FILING_CODE_SYNC_TIMEZONE` | IANA zone, default `America/New_York`; record daylight-saving behavior |

The existing deployment guide records upstream production refresh at 02:13 and
test at 19:35 Eastern. It recommends production copy around 04:30; Fly staging
using the test proxy runs at 21:30. Confirm the upstream schedule with its
operator before changing a target deployment. These are different source/schedule
choices, not two interchangeable sources.

## Daily operating checklist

1. Confirm at least one `code_index_worker` is running against the same application
   version/database as the web service. Its command must include `--daily` to honor
   the configured time and process staff jobs; `--interval` does neither. Apply
   migrations before starting the updated worker. Check disk capacity and
   label-backfill needs before first build.
2. Sign in as a superuser at the private `LITEFILE_STAFF_PATH`, open **Filing codes**,
   and inspect each jurisdiction's catalog/index freshness, recent run status,
   pending jobs and errors. `is_staff` or the aggregate-reporting role alone does
   not grant these tools. Staff use local password/TOTP, not court credentials.
3. Compare the last successful run with the expected upstream/local schedules.
   A successful unchanged-court run can finish in seconds; a long run needs
   progress/worker/disk inspection before calling it stalled. Record last success,
   court/path counts and error category without payloads or credentials.
4. If a run failed or the queue is not progressing, inspect worker health,
   database connectivity, reader grants, upstream completion and free disk.
   The shipped worker uses `--retry-interval 900` for 15-minute failed-state
   retries; the command default without that option is 60 seconds. Staff jobs
   are polled every 30 seconds. A daily-worker restart marks previously running
   jobs failed with “Interrupted by a worker restart”; check the last good catalog
   and request the needed retry. Startup builds jurisdictions without a current
   index. Escalate repeated failures to the assigned operator/proxy contact.
5. Check a representative new/existing-case search in the affected jurisdiction
   and apply its result against the live lists. Recheck code-bound guidance and
   name-bound availability rules after catalog drift.

A first incomplete catalog leaves search unavailable; ordinary court lists
remain available and the open modal retries search. Results older than two days
show an out-of-date notice. Selected paths are checked against live lists.
A changed proxy URL or search-rule revision requires a compatible current index.
Do not describe a stale index as legal confirmation of a choice.

## Choose the recovery operation

| Operation | Reads upstream? | Use and success indicator |
| --- | --- | --- |
| **Resync codes** | Yes | Copy changed courts now, then index them; queued job finishes, last-success freshness advances, no errors. An unchanged source can yield zero changed paths |
| **Rebuild code search indexes** | No | Rebuild from the local copy after indexed-rule changes; index matches current rules and representative queries work |
| `refresh_filing_code_index --build-labels` | No | Backfill missing compact label catalogs used by grouped search; label build completes and label-backed results appear. Daily-worker startup already does this; indexes with labels are skipped. This is not an upstream refresh |

Staff buttons can target one or all jurisdictions, queue work and record an audit
entry. If the worker is stopped, a queued button is not a completed operation.
Prefer these buttons while the daily worker is running so it owns the job.
Coordinate one-off commands with the operator rather than starting an overlapping
copy/rebuild alongside it. Commands below run from `efile_app` in the target environment:

```bash
uv run python manage.py migrate --noinput
uv run python manage.py refresh_filing_code_index --dry-run --jurisdiction vermont
uv run python manage.py refresh_filing_code_index --jurisdiction vermont
uv run python manage.py refresh_filing_code_index --rebuild --jurisdiction vermont
uv run python manage.py refresh_filing_code_index --build-labels --jurisdiction vermont
```

Select the command needed, rather than running every recovery operation. Dry-run
reports proposed changes; it is not validation of a completed rebuild. Success
includes the expected staff run/command result and usable searches, not merely a
worker process existing. Empty upstream filing lists stop the copy and preserve
the old catalog. Investigate a half-finished upstream update and retry; do not
discard the last good catalog or change to a different environment to make a
failure disappear. A bulk/legacy fallback needs the operator to confirm it uses
the same target source.

## Reader, migration and capacity prerequisites

Use a dedicated `litefile_codes_reader` with only `SELECT` on the five proxy code
tables: `location`, `installedversion`, `casecategory`, `casetype`, `filing`.
Retain the deployment guide's server-role restrictions and transaction-level
`READ ONLY`, `REPEATABLE READ` behavior; do not substitute the proxy's broader
application credentials. If an upstream migration recreates a table, its
database owner must re-grant the reader's access and confirm a read-only sync.
Ordinary upstream row refreshes retain grants.

Apply migrations before serving updated search readers or launching updated
workers. Check database and temporary-sort free space before label backfill,
large updates and rebuilds; a rewrite can temporarily need about the table's
size again. Coordinate long work with deployment operations and preserve the
old complete catalog on failure.

The storage note measured staging on October 10: 7.7 GB total, 7.6 GB in
`efile_filingcodepath`. Its roughly 0.5 GB label-size projection comes from a
synthetic benchmark; it is not measured production capacity. The deployment
guide's two-minute Vermont test build is also not a production service objective.
Measure disk, temporary-space needs and duration in the target environment.
[#314](https://github.com/SuffolkLITLab/LITEFile/issues/314) is separate optimization
work, not a prerequisite for the existing search or document finder.

Indexed search terms/explanations require restart and index rebuild. Response-only
definitions/facets/case guidance/glossary require clearing their web-process caches
by restart. Existing State YAML is reloaded on file metadata change; adding a
jurisdiction requires application restart. See the [maintained-data inventory](../partners-courts/maintained-data.md)
for the correct refresh per asset.

## Escalation record

Record environment, deployed commit, jurisdiction, expected run time, last good
run/index, pending/failed job state, worker uptime, disk and grant check results,
sanitized error, representative query and recovery attempt. Link the incident to
the asset's register row and assign the next check. Keep URLs containing credentials,
database connection strings and real filing data out of tickets/screenshots.
