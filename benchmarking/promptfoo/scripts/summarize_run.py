#!/usr/bin/env python3
"""Turn raw Promptfoo result JSON into stable lab-notebook tables."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def mean(values):
    return sum(values) / len(values) if values else 0.0


def prompt_dimensions(label):
    parts = label.split(":")
    return {
        "prompt_version": parts[1] if len(parts) > 1 else "",
        "input_mode": ":".join(parts[2:]) if len(parts) > 2 else "",
    }


def result_rows(suite, document):
    eval_id = document.get("evalId", "")
    for result in document["results"]["results"]:
        response = result.get("response") or {}
        token_usage = result.get("tokenUsage") or response.get("tokenUsage") or {}
        prompt_label = result["prompt"].get("label", "")
        metadata = result.get("metadata", {})
        yield {
            "suite": suite,
            "eval_id": eval_id,
            "provider_id": result["provider"]["id"],
            "provider_label": result["provider"].get("label", result["provider"]["id"]),
            "prompt_label": prompt_label,
            **prompt_dimensions(prompt_label),
            "case_id": metadata.get("case_id", ""),
            "variant": metadata.get("variant", ""),
            "classification_level": metadata.get("classification_level", ""),
            "score": float(result.get("score") or 0),
            "passed": bool(result.get("success")),
            "api_error": bool(
                response.get("error") or result.get("failureReason") == "ERROR"
            ),
            "latency_ms": result.get("latencyMs") or response.get("latencyMs") or 0,
            "cost": result.get("cost") or response.get("cost") or 0,
            "prompt_tokens": token_usage.get("prompt", 0),
            "completion_tokens": token_usage.get("completion", 0),
            "total_tokens": token_usage.get("total", 0),
        }


def field_rows(suite, document):
    for result in document["results"]["results"]:
        grading_result = result.get("gradingResult") or {}
        outer = grading_result.get("componentResults", [])
        components = outer[0].get("componentResults", []) if outer else []
        for component in components:
            reason = component.get("reason", "")
            prompt_label = result["prompt"].get("label", "")
            metadata = result.get("metadata", {})
            yield {
                "suite": suite,
                "provider_label": result["provider"].get(
                    "label", result["provider"]["id"]
                ),
                "prompt_label": prompt_label,
                **prompt_dimensions(prompt_label),
                "case_id": metadata.get("case_id", ""),
                "variant": metadata.get("variant", ""),
                "classification_level": metadata.get("classification_level", ""),
                "field": reason.split(":", 1)[0] if ":" in reason else "",
                "passed": bool(component.get("pass")),
                "score": float(component.get("score") or 0),
                "reason": reason,
            }


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    for values, members in sorted(groups.items()):
        result = dict(zip(keys, values, strict=True))
        result.update(
            {
                "runs": len(members),
                "mean_score": round(mean([row["score"] for row in members]), 6),
                "passes": sum(row["passed"] for row in members),
                "errors": sum(row["api_error"] for row in members),
                "mean_latency_ms": round(mean([row["latency_ms"] for row in members])),
                "total_tokens": sum(row["total_tokens"] for row in members),
                "total_cost": round(sum(row["cost"] for row in members), 8),
            }
        )
        yield result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "results",
        nargs="+",
        help="Named result in suite=path form, for example text=results/text.json",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    documents = []
    for spec in args.results:
        suite, separator, raw_path = spec.partition("=")
        if not separator:
            raise SystemExit(f"Result must use suite=path form: {spec}")
        documents.append(
            (suite, json.loads(Path(raw_path).read_text(encoding="utf-8")))
        )

    rows = [
        row for suite, document in documents for row in result_rows(suite, document)
    ]
    fields = [
        row for suite, document in documents for row in field_rows(suite, document)
    ]
    write_csv(args.output / "result_rows.csv", rows)
    write_csv(args.output / "field_outcomes.csv", fields)
    write_csv(
        args.output / "scores_by_model_prompt.csv",
        aggregate(rows, ["suite", "provider_label", "prompt_label"]),
    )
    write_csv(
        args.output / "scores_by_case.csv",
        aggregate(rows, ["suite", "case_id", "variant"]),
    )
    write_csv(
        args.output / "scores_by_input_mode.csv",
        aggregate(rows, ["suite", "input_mode", "prompt_version"]),
    )
    write_csv(
        args.output / "scores_by_document_input.csv",
        aggregate(rows, ["suite", "variant", "input_mode", "prompt_version"]),
    )
    if any(row["classification_level"] for row in rows):
        write_csv(
            args.output / "scores_by_classification_level.csv",
            aggregate(rows, ["suite", "classification_level", "input_mode"]),
        )

    summary = {
        "suites": {
            suite: {
                "eval_id": document.get("evalId"),
                "runs": len(document["results"]["results"]),
                "passes": document["results"]["stats"]["successes"],
                "failures": document["results"]["stats"]["failures"],
                "errors": document["results"]["stats"]["errors"],
                "mean_score": round(
                    mean([row["score"] for row in rows if row["suite"] == suite]), 6
                ),
                "token_usage": document["results"]["stats"].get("tokenUsage", {}),
            }
            for suite, document in documents
        }
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
