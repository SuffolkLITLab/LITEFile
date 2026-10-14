"""Read-only, court-scoped code search for the document classifier."""

from contextlib import contextmanager

from django.db import DatabaseError, connection, transaction

from efile.services.filing_code_search import current_index, search_paths

MAX_SEARCH_ROUNDS = 2
MAX_QUERY_LENGTH = 200
MAX_RESULTS = 10
MAX_SEARCH_PATHS = 50
SEARCH_TIMEOUT_MS = 2000
FACETS = {"case category": "case_category", "case type": "case_type", "filing type": "filing_type"}


@contextmanager
def search_timeout():
    """Bound PostgreSQL work and roll back errors without poisoning a caller's transaction."""
    with transaction.atomic():
        previous = None
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
                previous = cursor.fetchone()[0]
                limit = min(int(previous), SEARCH_TIMEOUT_MS) if int(previous) else SEARCH_TIMEOUT_MS
                cursor.execute("SELECT set_config('statement_timeout', %s, true)", [str(limit)])
        yield
        if previous is not None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('statement_timeout', %s, true)", [previous])


def search_classification_candidates(*, jurisdiction, query, level, filing_phase, selections, references, source_url):
    """Retrieve hints, never extend the authoritative live candidate list.

    The application supplies all scope, not the model. A stale cached route or
    renamed code cannot become a selectable reference through these results.
    No index is built and no provider request is made during this lookup.
    """
    if level not in FACETS or filing_phase not in {"initial", "subsequent"}:
        return {
            "status": "unavailable",
            "reason": "Search requires a selected court and known filing phase.",
            "results": [],
        }
    court = selections.get("court", {})
    if court.get("status") != "selected":
        return {"status": "unavailable", "reason": "Search requires a selected court.", "results": []}
    try:
        with search_timeout():
            index = current_index(jurisdiction)
            if index is None or index.source_url.rstrip("/") != source_url.rstrip("/"):
                return {"status": "unavailable", "reason": "No matching search index is available.", "results": []}
            data = search_paths(
                index,
                query,
                initial=filing_phase == "initial",
                court=court["route_key"],
                category=selections.get("case category", {}).get("route_key"),
                case_type=selections.get("case type", {}).get("route_key"),
                limit=MAX_SEARCH_PATHS,
                include_total=False,
                include_details=False,
            )
    except DatabaseError:
        return {"status": "unavailable", "reason": "The code search index could not be read.", "results": []}

    live_refs = {(str(value["route_key"]), value["name"]): ref for ref, value in references.items()}
    results = []
    seen = set()
    for row in data["results"]:
        candidate = row[FACETS[level]]
        reference = live_refs.get((str(candidate["code"]), candidate["name"]))
        if not reference or reference in seen or row.get("unavailable"):
            continue
        seen.add(reference)
        results.append(
            {
                "selection_ref": reference,
                "case_category": row["case_category"]["name"],
                "case_type": row["case_type"]["name"],
                "filing_type": row["filing_type"]["name"],
                "explanation": row["explanation"],
                "explanation_source": row["explanation_source"],
            }
        )
        if len(results) == MAX_RESULTS:
            break
    return {
        "status": "ok",
        "results": results,
        "index_refreshed_at": index.refreshed_at.isoformat(),
        "reason": "Cached search hints only; confirm against the source document and live candidates.",
    }
