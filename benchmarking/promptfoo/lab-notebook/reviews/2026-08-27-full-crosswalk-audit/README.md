# Full crosswalk audit

## Result

The crosswalk is structurally valid, but it is not yet a fully verified
form-to-Tyler mapping. This audit checked the complete current registry without
changing the production crosswalk.

| Check | Result | Meaning |
| --- | ---: | --- |
| Registry records | 891 | 764 forms and 127 non-form documents |
| Candidate mappings | 2,908 | 2,645 active associations plus non-applicable records |
| Complete taxonomy paths | 651 | Have category, case type, and filing type names |
| Live court-specific checks | 1,700 | Complete paths expanded across their recorded court scopes |
| Current live paths | 864 | The complete named hierarchy resolved at the audit endpoint |
| Missing live paths | 836 | At least one recorded name or parent relationship was absent |
| Incomplete/unscoped mappings | 1,753 | Not testable until parent names and court scope are complete |
| Persistent live errors | 0 | One timeout was retried successfully as current |

The live result is a hierarchy-existence test, not a semantic approval. A
`current` result means that the recorded category, case type, and filing type
names can be traversed for the recorded court in the current test environment.
It does not prove that the form belongs to that path.

## Source coverage

The source audit checked 447 unique URLs. 373 were reachable and 74 returned
HTTP errors; there were no transport errors. 393 registry records have no
source URL at all. The source failures and their canonical form IDs are in
[`source-audit.json`](./artifacts/source-audit.json).

## What remains

1. Review the 2,645 active form-to-taxonomy associations. The ten Illinois
   printed-code assignments are human-reviewed, but that does not verify their
   filing routes. The crosswalk currently has zero human-verified taxonomy
   mappings.
2. Triage the 836 missing complete paths. Many are stale candidate suggestions
   or incorrect parent relationships, especially in Vermont and Illinois; they
   should be corrected, narrowed, or removed rather than automatically remapped
   to a similar label.
3. Complete the 1,753 partial observations and 296 not-checked mappings with
   current court scope, category, case type, filing type, and filing phase.
4. Repair or replace the 74 failed source URLs and add provenance for the 393
   forms that have no source URL.
5. Add reviewed taxonomy associations for the three Illinois code-backed
   identity records that intentionally have empty mappings: `IL-ATJ-561.1`,
   `IL-ATJ-105.3`, and `IL-AOIC-1601.1`.
6. For every accepted mapping, record the reviewer, date, source evidence,
   court scope, filing phase, and any discriminator needed to select one path
   among several valid paths.

## Reproduction

From `benchmarking/promptfoo`:

```bash
python scripts/normalize_form_code_crosswalk.py --check
python scripts/audit_form_code_crosswalk.py
python scripts/audit_form_code_crosswalk.py --sources \
  --output lab-notebook/reviews/2026-08-27-full-crosswalk-audit/artifacts/source-audit.json
python scripts/audit_form_code_crosswalk.py --live --include-suggestions \
  --output lab-notebook/reviews/2026-08-27-full-crosswalk-audit/artifacts/live-audit.json
```

The complete live report is in
[`live-audit.json`](./artifacts/live-audit.json). Its one timeout was retried
against the same endpoint and resolved to `current`; the raw report retains the
original result for auditability.
