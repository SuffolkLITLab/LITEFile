"""Copy filing codes straight from the EFSP proxy's codes database, then index them.

The proxy refreshes its codes from Tyler once a day. LITEFile reads the same
tables over a read-only connection -- the queries match the proxy's own
filing-catalog export -- and keeps a copy per court
(``FilingCodeCourtCatalog``). The search index is built from that copy, so a
search-rules change needs only a rebuild, never another trip to the EFSP.

Every read happens inside one READ ONLY, REPEATABLE READ transaction: the
court list and every court's tables come from the same snapshot, and the
database refuses any write. (Supabase's pooler ignores connection-level
settings, so read-only is set per transaction.)
"""

from __future__ import annotations

import psycopg
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from psycopg.rows import dict_row

from efile.models import FilingCodeCourtCatalog, FilingCodeIndex
from efile.services.court_selection import is_non_filing_court
from efile.services.filing_code_sync import synchronize_index, validate_export

# Each court's revision changes when its name or the installed version of any of
# its three code lists does: the proxy's own manifest query.
COURTS_SQL = """
SELECT l.code, l.name, (l.initial ILIKE 'true' OR l.subsequent ILIKE 'true') AS fileable,
  count(v.installedversion) AS versions,
  md5(jsonb_build_array(l.name, jsonb_object_agg(v.codelist, v.installedversion)
    FILTER (WHERE v.codelist IS NOT NULL))::text) AS revision
FROM location l LEFT JOIN installedversion v
  ON v.jurisdiction=l.jurisdiction AND v.location=l.code
  AND v.codelist IN ('casecategorycodes.zip', 'casetypecodes.zip', 'filingcodes.zip')
  AND btrim(v.installedversion) <> ''
WHERE l.jurisdiction=%s
GROUP BY l.code, l.name, l.initial, l.subsequent ORDER BY l.code
"""
CATEGORIES_SQL = """
SELECT code, name FROM casecategory WHERE jurisdiction=%s AND location=%s
  AND ecfcasetype != 'CriminalCase' ORDER BY code, name
"""
CASE_TYPES_SQL = """
SELECT code, name, casecategory AS case_category, coalesce(lower(initial)='true', false) AS initial
FROM casetype WHERE jurisdiction=%s AND location=%s ORDER BY casecategory, code, name
"""
FILING_TYPES_SQL = """
SELECT code, name, casecategory AS case_category, casetypeid AS case_type, filingtype AS timing
FROM filing WHERE jurisdiction=%s AND location=%s AND iscourtuseonly='False'
  AND filingtype IN ('Initial', 'Subsequent', 'Both')
ORDER BY code, casecategory, casetypeid, filingtype, name
"""


class EfspCodesDatabase:
    """A read-only snapshot of one jurisdiction's codes in the EFSP database."""

    def __init__(self, jurisdiction):
        if not settings.EFSP_CODES_DATABASE_URL:
            raise ValueError("Set EFSP_CODES_DATABASE_URL to copy codes from the EFSP database.")
        self.jurisdiction = jurisdiction

    def __enter__(self):
        self.connection = psycopg.connect(
            settings.EFSP_CODES_DATABASE_URL,
            connect_timeout=30,
            application_name="litefile-code-copy",
            row_factory=dict_row,
        )
        try:
            self.connection.read_only = True
            self.connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            self.snapshot = self.connection.transaction()
            self.snapshot.__enter__()
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if (cursor.fetchone() or {}).get("transaction_read_only") != "on":
                    raise ValueError("The EFSP codes database connection is not read only; refusing to continue.")
        except BaseException:
            # __exit__ never runs when __enter__ fails: close here.
            self.connection.close()
            raise
        return self

    def __exit__(self, *exc_info):
        try:
            self.snapshot.__exit__(*exc_info)
        finally:
            self.connection.close()

    def _rows(self, sql, *params):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, (self.jurisdiction, *params))
            return cursor.fetchall()

    def manifest(self):
        courts = {}
        for row in self._rows(COURTS_SQL):
            # Tyler-internal rows (Illinois' "System", flagged fileable for
            # existing cases but holding no code lists) never block a copy.
            if is_non_filing_court(row["name"]):
                continue
            if row["versions"] != 3:
                if row["fileable"]:
                    # As the proxy's export does: a filing court with missing code
                    # lists means Tyler's update is mid-way. Copy nothing.
                    raise ValueError(f"Incomplete installed filing catalog for court {row['code']}; try again later.")
                continue
            courts[row["code"]] = {key: row[key] for key in ("code", "name", "revision")}
        if not courts:
            raise ValueError("No filing courts in the EFSP codes database; keeping the previous copy.")
        return courts

    def court(self, court):
        data = {
            "court": court,
            "categories": self._rows(CATEGORIES_SQL, court["code"]),
            "case_types": self._rows(CASE_TYPES_SQL, court["code"]),
            "filing_types": self._rows(FILING_TYPES_SQL, court["code"]),
        }
        validate_export(data)
        return data


def copy_codes(jurisdiction, *, progress=None, force=(), dry_run=False):
    """Copy courts whose EFSP revision changed (plus ``force``); drop courts the EFSP no longer has.

    Each court is saved as it is read, so memory holds one court at a time and
    the local database is never locked for the whole copy. A court that
    suddenly has no filing types almost always means a half-finished EFSP
    update, so the copy stops and keeps the old one.
    """
    existing = {
        row["code"]: row
        for row in FilingCodeCourtCatalog.objects.filter(jurisdiction=jurisdiction).values(
            "code", "revision", "filing_count"
        )
    }
    changed = 0
    with EfspCodesDatabase(jurisdiction) as source:
        courts = source.manifest()
        if unknown := set(force) - set(courts):
            raise ValueError("Not filing courts in the EFSP codes database: " + ", ".join(sorted(unknown)))
        for code, court in courts.items():
            old = existing.get(code)
            if old and old["revision"] == court["revision"] and code not in force:
                continue
            data = source.court(court)
            count = len(data["filing_types"])
            if old and old["filing_count"] and not count and code not in force:
                raise ValueError(
                    f"{court['name']} ({code}) now has no filing types (had {old['filing_count']}); keeping the "
                    "previous copy. If that's expected, resync with this court forced."
                )
            if progress:
                progress(f"{court['name']} ({code}): {old['filing_count'] if old else 'new'} -> {count} filing types")
            changed += 1
            if dry_run:
                continue
            FilingCodeCourtCatalog.objects.update_or_create(
                jurisdiction=jurisdiction,
                code=code,
                defaults={
                    "name": court["name"],
                    "revision": court["revision"],
                    "data": data,
                    "filing_count": count,
                    "copied_at": timezone.now(),
                },
            )
    removed = set(existing) - set(courts)
    if removed and not dry_run:
        FilingCodeCourtCatalog.objects.filter(jurisdiction=jurisdiction, code__in=removed).delete()
    if progress:
        progress(f"{changed} changed courts, {len(removed)} removed, {len(courts) - changed} unchanged")
    return {"courts": len(courts), "changed": changed, "removed": len(removed)}


class LocalCopyCatalog:
    """The copied courts, in the shape ``synchronize_index`` reads."""

    def __init__(self, jurisdiction):
        self.jurisdiction = jurisdiction

    def manifest(self):
        courts = {
            row["code"]: row
            for row in FilingCodeCourtCatalog.objects.filter(jurisdiction=self.jurisdiction)
            .order_by("code")
            .values("code", "name", "revision")
        }
        if not courts:
            raise ValueError("No copied codes yet for this jurisdiction. Resync codes first.")
        return courts

    def court(self, court):
        return FilingCodeCourtCatalog.objects.get(jurisdiction=self.jurisdiction, code=court["code"]).data

    def close(self):
        pass


def resync(jurisdiction, *, progress=None, force=(), dry_run=False):
    """Copy changed courts from the EFSP, then update the index for those courts."""
    copied = copy_codes(jurisdiction, progress=progress, force=force, dry_run=dry_run)
    if dry_run:
        return copied["changed"]
    # An index built from older rules is replaced in full; otherwise only changed courts are.
    return synchronize_index(jurisdiction, catalog=LocalCopyCatalog(jurisdiction), progress=progress, force=force)


def rebuild(jurisdiction, *, progress=None):
    """Rebuild the whole search index from the local copy, without contacting the EFSP."""
    return synchronize_index(jurisdiction, catalog=LocalCopyCatalog(jurisdiction), progress=progress, full=True)


def status(jurisdiction):
    """What the staff page shows for one jurisdiction."""
    copies = FilingCodeCourtCatalog.objects.filter(jurisdiction=jurisdiction)
    index = FilingCodeIndex.objects.filter(jurisdiction=jurisdiction).first()
    latest = copies.order_by("-copied_at").values_list("copied_at", flat=True).first()
    return {
        "jurisdiction": jurisdiction,
        "copied_courts": copies.count(),
        "copied_at": latest,
        "indexed_at": index.refreshed_at if index else None,
        "indexed_paths": sum(item.get("count", 0) for item in (index.court_snapshots or {}).values()) if index else 0,
    }


def run_jobs(jurisdictions, *, log=print):
    """Run queued staff requests, oldest first, until none are left."""
    from efile.models import FilingCodeJob

    while True:
        job = FilingCodeJob.objects.filter(status=FilingCodeJob.Status.QUEUED).order_by("requested_at").first()
        if job is None:
            return
        # Claim it with a conditional update, which works on SQLite and Postgres alike.
        claimed = FilingCodeJob.objects.filter(pk=job.pk, status=FilingCodeJob.Status.QUEUED).update(
            status=FilingCodeJob.Status.RUNNING, started_at=timezone.now()
        )
        if not claimed:
            continue
        lines, failed = [], []
        for jurisdiction in [job.jurisdiction] if job.jurisdiction else jurisdictions:
            try:
                count = (rebuild if job.kind == FilingCodeJob.Kind.REBUILD else resync)(jurisdiction)
                lines.append(f"{jurisdiction}: {count} filing paths saved")
            except Exception as error:  # Report every failure on the job; keep the worker alive.
                failed.append(jurisdiction)
                lines.append(f"{jurisdiction}: failed; previous index kept. {error}")
            log(lines[-1])
        with transaction.atomic():
            FilingCodeJob.objects.filter(pk=job.pk).update(
                status=FilingCodeJob.Status.FAILED if failed else FilingCodeJob.Status.SUCCEEDED,
                finished_at=timezone.now(),
                message="\n".join(lines),
            )
