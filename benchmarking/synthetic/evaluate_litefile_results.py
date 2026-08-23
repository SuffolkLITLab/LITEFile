#!/usr/bin/env python3
"""Summarize LITEFile extraction results against non-gold synthetic corpus expectations.

Usage:
  python evaluate_litefile_results.py litefile_results.jsonl

This is deliberately diagnostic, not a pass/fail gold scorer.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
expect = {
    r["id"]: r
    for r in map(json.loads, (ROOT / "extractability.jsonl").read_text().splitlines())
}


def norm(x):
    return re.sub(r"[^a-z0-9]+", " ", str(x).casefold()).strip()


if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <extraction_results.jsonl>", file=sys.stderr)
    sys.exit(1)

rows = []
for line in Path(sys.argv[1]).read_text().splitlines():
    r = json.loads(line)
    if "result" not in r:
        continue
    e = expect[r["id"]]
    got = r["result"] or {}
    direct = []
    for k, v in e["directly_visible_or_labeled"].items():
        g = got.get(k)
        direct.append((k, bool(g), norm(v) == norm(g) if g else False))
    sem = []
    for k in e["semantic_but_reasonable"].keys():
        g = got.get(k)
        sem.append((k, bool(g), g))
    extras = {k: got.get(k) for k in e["do_not_require"] if got.get(k)}
    rows.append((r["id"], r["variant"], direct, sem, extras))

for id_val, variant, direct, sem, extras in rows:
    present = sum(p for _, p, _ in direct)
    exact = sum(x for *_, x in direct)
    print(
        f"{id_val:5} {variant:11} direct-present {present}/{len(direct)} exact {exact}/{len(direct)}"
    )
    missing = [k for k, p, _ in direct if not p]
    if missing:
        print("  missing direct:", ", ".join(missing))
    if sem:
        print("  semantic:", "; ".join(f"{k}={g!r}" for k, _, g in sem))
    if extras:
        print("  non-required inference:", extras)
