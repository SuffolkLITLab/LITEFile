"""Incremental public-catalog imports across the proxy's HTTP service boundary.

One small manifest identifies changed courts. A compact export contains their
code tables and relationships; expansion and search rules belong to LITEFile.
Downloads and validation finish before a transaction replaces changed courts.
"""

import gzip
import hashlib
import json
from contextlib import closing
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from django.db import connection, transaction
from django.utils import timezone
from psycopg import Cursor
from psycopg.types.json import Jsonb

from efile.db_expressions import CourtCode
from efile.models import FilingCodeIndex, FilingCodePath
from efile.services.court_selection import is_non_filing_court
from efile.services.filing_code_search import (
    FACETS,
    CodeCatalog,
    explanation_for,
    packed,
    rules,
    search_tokens,
    source_url,
    stems,
    words,
)


class BulkCodeCatalog(CodeCatalog):
    def __init__(self, jurisdiction):
        super().__init__(jurisdiction)
        self.jurisdiction = jurisdiction
        self.base = f"{source_url()}/jurisdictions/{jurisdiction}/codes/filing_catalog"

    def read(self, suffix=""):
        with self.session.get(self.base + suffix, timeout=self.timeout) as response:
            if response.status_code == 404 and not suffix:
                raise ValueError("Deploy the proxy filing_catalog API first, or explicitly use --legacy-crawl.")
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or data.get("version") != 1 or data.get("jurisdiction") != self.jurisdiction:
            raise ValueError("Unsupported or wrong-jurisdiction filing catalog export")
        return data

    def manifest(self):
        data = self.read()
        if not isinstance(data.get("courts"), list) or not data["courts"]:
            raise ValueError("Empty or invalid filing catalog manifest; keeping the previous index")
        courts = {}
        for court in data["courts"]:
            _option(court)
            revision = court.get("revision")
            if not isinstance(revision, str) or not revision:
                raise ValueError("Invalid court catalog revision")
            if court["code"] in courts:
                raise ValueError("Duplicate court in filing catalog manifest")
            if not is_non_filing_court(court["name"]):
                courts[court["code"]] = court
        if not courts:
            raise ValueError("No filing courts in catalog manifest; keeping the previous index")
        return courts

    def court(self, court):
        data = self.read(f"/courts/{quote(court['code'], safe='')}")
        if data.get("court") != court:
            raise ValueError("Court export does not match its manifest revision")
        validate_export(data)
        return data


def _option(value):
    if not isinstance(value, dict) or any(
        not isinstance(value.get(key), str) or not value[key] for key in ("code", "name")
    ):
        raise ValueError("Invalid option in filing catalog export")


def validate_export(data):
    for table in ("categories", "case_types", "filing_types"):
        if not isinstance(data.get(table), list):
            raise ValueError("Missing code table in court export")
        for row in data[table]:
            _option(row)
            if table != "categories" and (
                "case_category" not in row
                or row["case_category"] is not None
                and not isinstance(row["case_category"], str)
            ):
                raise ValueError("Invalid category relationship in court export")
            if table == "case_types" and type(row.get("initial")) is not bool:
                raise ValueError("Invalid case-type timing in court export")
            if table == "filing_types" and (
                "case_type" not in row
                or row["case_type"] is not None
                and not isinstance(row["case_type"], str)
                or row.get("timing") not in ("Initial", "Subsequent", "Both")
            ):
                raise ValueError("Invalid filing-type relationship or timing in court export")


def export_entries(data, jurisdiction):
    """Match the existing proxy filters, including its specific-before-generic fallback."""
    court = {key: data["court"][key] for key in ("code", "name")}
    categories = {row["code"]: row for row in data["categories"]}
    case_types = {(row["case_category"], row["code"]): row for row in data["case_types"]}
    for initial in (True, False):
        # The proxy's category endpoint gates each timing on at least one case
        # type with that initial flag. Subsequent type lists then include all
        # case types in those categories, matching its existing SQL exactly.
        offered_categories = {row["case_category"] for row in case_types.values() if row["initial"] == initial}
        by_category, by_type, generic = {}, {}, []
        for filing in data["filing_types"]:
            if filing["timing"] not in (("Initial", "Both") if initial else ("Subsequent", "Both")):
                continue
            if filing["case_type"] == "":
                if filing["case_category"] == "":
                    generic.append(filing)
                elif filing["case_category"] is not None:
                    by_category.setdefault(filing["case_category"], []).append(filing)
            elif filing["case_type"] is not None:
                by_type.setdefault(filing["case_type"], []).append(filing)
        for case_type in case_types.values():
            category = categories.get(case_type["case_category"])
            if category is None or category["code"] not in offered_categories or initial and not case_type["initial"]:
                continue
            # Filtered list APIs deduplicate options by code after choosing specific or generic lists.
            selected = by_category.get(category["code"], []) + by_type.get(case_type["code"], [])
            filings = {row["code"]: row for row in selected or generic}
            for filing in filings.values():
                path = dict(zip(FACETS, (court, category, case_type, filing), strict=True))
                path = {facet: {key: value[key] for key in ("code", "name")} for facet, value in path.items()}
                terms = {facet: search_tokens(path[facet]["name"], jurisdiction) for facet in FACETS}
                all_terms = set.union(*terms.values())
                all_terms.update(token for facet in FACETS for token in stems(path[facet]["code"]))
                explanation, source = explanation_for(jurisdiction, path, initial)
                yield dict(
                    **path,
                    initial=initial,
                    search_text=packed(all_terms),
                    filing_terms=packed(terms["filing_type"]),
                    case_terms=packed(terms["case_category"] | terms["case_type"]),
                    explanation=explanation,
                    explanation_source=source,
                )


def _stage(data, jurisdiction, path):
    vocabulary, tokens, count = set(), set(), 0
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as stream:
        for entry in export_entries(data, jurisdiction):
            stream.write(json.dumps(entry) + "\n")
            tokens.update(entry["search_text"].split())
            vocabulary.update(word for facet in FACETS for word in words(entry[facet]["name"]))
            count += 1
    return {"count": count, "words": sorted(vocabulary), "tokens": sorted(tokens)}


def _insert_paths(index, snapshot, count, progress):
    """COPY on Postgres; bounded ORM batches on SQLite. IDs come from each database's sequence."""
    saved = 0
    if connection.vendor == "postgresql":
        fields = [field for field in FilingCodePath._meta.concrete_fields if not field.primary_key]
        columns = ", ".join(connection.ops.quote_name(field.column) for field in fields)
        table = connection.ops.quote_name(FilingCodePath._meta.db_table)
        # Django defaults to psycopg's ClientCursor, which does not implement COPY.
        with Cursor(connection.connection) as cursor, cursor.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
            for line in snapshot:
                entry = json.loads(line)
                entry["index"] = index.pk
                copy.write_row(
                    [
                        Jsonb(entry[field.name]) if field.get_internal_type() == "JSONField" else entry[field.name]
                        for field in fields
                    ]
                )
                saved += 1
                if progress and saved % 100000 == 0:
                    progress(f"Saved {saved} of {count} changed filing paths")
    else:
        while batch := [FilingCodePath(index=index, **json.loads(line)) for line in islice(snapshot, 500)]:
            FilingCodePath.objects.bulk_create(batch, batch_size=500)
            saved += len(batch)
            if progress and saved % 100000 == 0:
                progress(f"Saved {saved} of {count} changed filing paths")


def synchronize_index(jurisdiction, *, progress=None, force=(), dry_run=False):
    """Re-download courts whose revision changed, plus any court codes in ``force``.

    ``dry_run`` downloads and checks everything, reports each changed court, and saves nothing.
    """
    started = timezone.now()
    baseline = FilingCodeIndex.objects.filter(jurisdiction=jurisdiction).first()
    previous = (
        baseline if baseline and baseline.source_url == source_url() and baseline.rules_digest == rules()[1] else None
    )
    snapshots = previous.court_snapshots if previous else {}
    # Stage every changed court before publishing anything. A failure preserves the whole old index.
    with closing(BulkCodeCatalog(jurisdiction)) as catalog, TemporaryDirectory(prefix="filing-sync-") as directory:
        courts = catalog.manifest()
        if unknown := set(force) - set(courts):
            raise ValueError("Not filing courts in the proxy's catalog manifest: " + ", ".join(sorted(unknown)))
        next_snapshots, staged = {}, {}
        downloaded = False
        for code, court in courts.items():
            old = snapshots.get(code)
            if old and old["revision"] == court["revision"] and code not in force:
                next_snapshots[code] = old
                continue
            if progress:
                progress(f"Downloading changed court: {court['name']}")
            data = catalog.court(court)
            downloaded = True
            path = Path(directory) / f"{hashlib.sha256(code.encode()).hexdigest()}.json.gz"
            metadata = _stage(data, jurisdiction, path)
            # A court that loses every path almost always means the proxy served a half-loaded
            # court. Keep the old index rather than publishing an empty court.
            if old and old["count"] and not metadata["count"] and code not in force:
                raise ValueError(
                    f"{court['name']} ({code}) now has no filing paths (had {old['count']}); keeping the "
                    f"previous index. If that's expected, re-run with --court {code}."
                )
            if progress:
                progress(f"{court['name']} ({code}): {old['count'] if old else 'new'} -> {metadata['count']} paths")
            next_snapshots[code] = dict(metadata, revision=court["revision"])
            staged[code] = path
        if (downloaded or set(snapshots) - set(courts)) and catalog.manifest() != courts:
            raise ValueError("Proxy catalog changed during synchronization; keeping the previous index and retrying")
        if not sum(item["count"] for item in next_snapshots.values()):
            raise ValueError("No filing paths returned; keeping the previous index")
        vocabulary = set().union(*(set(item["words"]) for item in next_snapshots.values()))
        for concept in rules()[0]["concepts"].values():
            if jurisdiction in concept.get("jurisdictions", rules()[0]["jurisdictions"]):
                vocabulary.update(word for term in concept["terms"] for word in words(term))
        tokens = set().union(*(set(item["tokens"]) for item in next_snapshots.values()))
        count = sum(next_snapshots[code]["count"] for code in staged)
        if progress:
            progress(
                f"{len(staged)} changed courts; {len(courts) - len(staged)} unchanged; saving {count} filing paths"
            )
        if dry_run:
            return count
        with transaction.atomic():
            index, created = FilingCodeIndex.objects.get_or_create(
                jurisdiction=jurisdiction,
                defaults={"source_url": source_url(), "refreshed_at": started, "rules_digest": rules()[1]},
            )
            index = FilingCodeIndex.objects.select_for_update().get(pk=index.pk)
            if (
                index.refreshed_at > started
                or not created
                and (baseline is None or index.refreshed_at != baseline.refreshed_at)
            ):
                return 0
            if previous is None or not snapshots:
                # One-time bootstrap from legacy indexes, or a different source/rules revision.
                index.paths.all().delete()
            else:
                for code in set(snapshots) - set(courts) | set(staged):
                    index.paths.alias(catalog_court_code=CourtCode("court")).filter(catalog_court_code=code).delete()
            for code, path in staged.items():
                with gzip.open(path, "rt", encoding="utf-8") as snapshot:
                    _insert_paths(index, snapshot, next_snapshots[code]["count"], progress)
            index.source_url = source_url()
            index.rules_digest = rules()[1]
            index.refreshed_at = started
            index.court_snapshots = next_snapshots
            index.vocabulary = {"words": sorted(vocabulary), "tokens": sorted(tokens)}
            index.save()
    return count
