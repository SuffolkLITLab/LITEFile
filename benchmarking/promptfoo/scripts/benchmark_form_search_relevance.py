#!/usr/bin/env python3
"""Replay a frozen, curated cross-state form-search corpus through search_paths.

Run from efile_app with the repo environment, for example:
  uv run python ../benchmarking/promptfoo/scripts/benchmark_form_search_relevance.py \
    --revision working --database /tmp/form-search-working.sqlite \
    --output /tmp/form-search-working.json
"""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--revision",
        required=True,
        help="Label recorded in output (e.g. HEAD-47f6afc or working-tree)",
    )
    parser.add_argument(
        "--database", required=True, type=Path, help="New isolated SQLite database path"
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(
            "../docs/developer-notes/fixtures/form-search-relevance-replay-2026-10-13.json"
        ),
    )
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "efile.settings")
    from django.conf import settings

    args.database.parent.mkdir(parents=True, exist_ok=True)
    if args.database.exists():
        parser.error(
            f"database path already exists; choose a new path: {args.database}"
        )
    settings.DATABASES["default"]["NAME"] = str(args.database.resolve())

    import django

    django.setup()
    from django.core.management import call_command
    from django.utils import timezone

    call_command("migrate", interactive=False, verbosity=0)

    from efile.models import FilingCodeIndex, FilingCodePath
    from efile.services.filing_code_search import (
        explanation_for,
        packed,
        search_paths,
        search_tokens,
        stems,
        words,
        rules,
    )

    try:
        from efile.services.filing_code_search import indexed_path
    except ImportError:  # Baseline predates the shared indexed_path helper.

        def indexed_path(jurisdiction, path, initial):
            terms = {
                facet: search_tokens(path[facet]["name"], jurisdiction)
                for facet in ("court", "case_category", "case_type", "filing_type")
            }
            all_terms = set.union(*terms.values())
            all_terms.update(
                token for facet in terms for token in stems(path[facet]["code"])
            )
            explanation, source = explanation_for(jurisdiction, path, initial)
            return dict(
                **path,
                initial=initial,
                search_text=packed(all_terms),
                filing_terms=packed(terms["filing_type"]),
                case_terms=packed(terms["case_category"] | terms["case_type"]),
                explanation=explanation,
                explanation_source=source,
            )

    fixture = json.loads(args.fixture.read_text())
    paths_by_state = {"illinois": [], "vermont": []}
    fixture_id_by_case_code = {}
    for path_number, spec in enumerate(fixture["paths"], start=1):
        state = spec["state"]
        fixture_id = spec["id"]
        if any(
            not str(spec[facet]["code"]).isdigit()
            for facet in ("category", "type", "filing")
        ):
            raise ValueError(
                f"Fixture facet codes must be opaque numeric identifiers: {fixture_id}"
            )
        # Opaque numeric synthetic codes keep fixture IDs and semantic labels out
        # of indexed code stems. Relevance IDs are mapped back after retrieval.
        synthetic_case_code = str(99000000 + path_number)
        fixture_id_by_case_code[synthetic_case_code] = fixture_id
        path = {
            "court": spec["court"],
            "case_category": spec["category"],
            "case_type": {**spec["type"], "code": synthetic_case_code},
            "filing_type": spec["filing"],
        }
        paths_by_state[state].append(indexed_path(state, path, spec["initial"]))

    indices = {}
    for state, entries in paths_by_state.items():
        courts = {entry["court"]["code"]: entry["court"]["name"] for entry in entries}
        tokens = sorted(
            {token for entry in entries for token in entry["search_text"].split()}
        )
        vocabulary = {
            word
            for entry in entries
            for facet in ("court", "case_category", "case_type", "filing_type")
            for word in words(entry[facet]["name"])
        }
        # Match production index construction on each revision: spelling
        # vocabulary includes every applicable search-concept term.
        config, _digest = rules()
        for concept in config["concepts"].values():
            if state in concept.get("jurisdictions", config["jurisdictions"]):
                vocabulary.update(
                    word for term in concept["terms"] for word in words(term)
                )
        vocabulary_words = sorted(vocabulary)
        index = FilingCodeIndex.objects.create(
            jurisdiction=state,
            source_url="https://efile-test.suffolklitlab.org",
            refreshed_at=timezone.now(),
            rules_digest="benchmark-curated-replay",
            vocabulary={"words": vocabulary_words, "tokens": tokens, "courts": courts},
            court_snapshots={},
        )
        FilingCodePath.objects.bulk_create(
            [FilingCodePath(index=index, **entry) for entry in entries], batch_size=500
        )
        indices[state] = index

    results = []
    for query_spec in fixture["queries"]:
        index = indices[query_spec["state"]]
        response = search_paths(
            index,
            query_spec["query"],
            initial=query_spec["initial"],
            limit=5,
        )
        top_ids = [
            fixture_id_by_case_code[row["case_type"]["code"]]
            for row in response["results"]
        ]
        expected = set(query_spec["relevant_ids"])
        retrieved = set(top_ids)
        positive = bool(expected)
        results.append(
            {
                "query_id": query_spec["id"],
                "state": query_spec["state"],
                "query": query_spec["query"],
                "initial": query_spec["initial"],
                "expected_relevant_ids": sorted(expected),
                "top1_ids": top_ids[:1],
                "top5_ids": top_ids,
                "total_results": response["total"],
                "top1_hit": bool(expected & set(top_ids[:1])) if positive else False,
                "top5_hit": bool(expected & retrieved) if positive else False,
                "recall_at_5": len(expected & retrieved) / len(expected)
                if positive
                else None,
                "no_result_expected": not positive,
                "no_result_correct": response["total"] == 0 if not positive else None,
                "corrected_terms": response["corrected_terms"],
            }
        )

    summaries = {}
    for state in paths_by_state:
        rows = [row for row in results if row["state"] == state]
        positives = [row for row in rows if row["expected_relevant_ids"]]
        negatives = [row for row in rows if not row["expected_relevant_ids"]]
        summaries[state] = {
            "fixture_paths": len(paths_by_state[state]),
            "queries": len(rows),
            "positive_queries": len(positives),
            "top1_hit_rate": sum(row["top1_hit"] for row in positives) / len(positives)
            if positives
            else None,
            "top5_hit_rate": sum(row["top5_hit"] for row in positives) / len(positives)
            if positives
            else None,
            "mean_recall_at_5": sum(row["recall_at_5"] for row in positives)
            / len(positives)
            if positives
            else None,
            "negative_queries": len(negatives),
            "negative_no_result_rate": sum(
                row["no_result_correct"] for row in negatives
            )
            / len(negatives)
            if negatives
            else None,
            "negative_false_result_queries": [
                row["query_id"] for row in negatives if not row["no_result_correct"]
            ],
        }
    output = {
        "version": 1,
        "revision": args.revision,
        "database": "isolated sqlite; fixture paths only",
        "fixture": args.fixture.as_posix(),
        "ran_at": timezone.now().isoformat(),
        "search_function": "efile.services.filing_code_search.search_paths",
        "summary": summaries,
        "results": results,
        "limitations": fixture.get("limitations", []),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "revision": args.revision,
                "summary": summaries,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
