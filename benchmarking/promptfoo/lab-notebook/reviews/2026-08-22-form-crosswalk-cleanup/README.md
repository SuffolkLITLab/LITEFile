# Form crosswalk cleanup review

## Purpose

Review the first-pass form-to-Tyler crosswalk, remove mechanically unsafe data,
and distinguish three different claims that had previously been conflated:

1. a label was seen somewhere in a Tyler environment
2. a complete named hierarchy is currently selectable for a court
3. the hierarchy is semantically correct for the identified form

Tyler taxonomy names are treated as the durable identifiers. Numeric taxonomy
keys and court route keys are environment observations only.

## Result

The crosswalk is structurally valid and useful as a form registry and candidate
research dataset. It is not yet an authoritative deterministic lookup because
none of its 2,908 mappings has received human association verification.

After removing obvious instruction and checklist packets from the filing-form
pool, the final crosswalk contains 888 registry documents: 761 court forms and
127 non-form documents. Of the court forms, 737 are marked e-fileable and 24
are not e-fileable.

The current mapping states are:

- 255 complete named paths current in every recorded court scope
- 341 complete paths absent from at least one claimed hierarchy at the latest
  check
- 1,753 partial observations without enough parent information for a full
  hierarchy check
- 296 candidates not checked in the catalog
- 263 non-applicable mappings belonging to non-form or non-efileable documents

All 2,645 active form associations remain `unverified_suggestion`. A current
catalog path is therefore a candidate for review, not a deterministic answer.

## Live taxonomy verification

The live audit made 1,700 court-specific hierarchy checks. It resolved every
category and case-type name to the test environment's current transient key,
used that key only to request the next level, and omitted numeric keys from the
report. There were 864 current court/path checks, 836 missing paths, and no
transport errors. Another 1,753 mappings were skipped because their hierarchy
is incomplete.

The failures exposed genuine candidate-generation problems, not merely catalog
drift. Examples included divorce forms paired with unrelated petitions and
probate forms placed under unrelated case types. Those paths are now marked
`not_current`; they remain in the data for provenance and rejection analysis
but must be excluded from runtime candidate selection.

## Form and source cleanup

Cleanup made these repeatable changes:

- standardized every form on a `source_urls` list
- converted 54 relative Illinois resource links to absolute official URLs
- added known per-form source pages from the synthetic benchmark manifest
- added explicit unknown revisions and document roles
- corrected seven form records misclassified by a title-only heuristic
- classified checklist, “Getting Started,” and similar packets as non-forms
- stopped marking instructions, guides, brochures, and checklists e-fileable
- trimmed outer whitespace from 29 taxonomy labels
- merged six mappings whose durable named identity was the same but whose
  observed surrogate keys or fees differed
- retained multiple observed fees and provenance notes on the merged records

The source audit checked 444 unique URLs: 373 were reachable and 71 returned an
HTTP error, all without transport failures. At the form level, 365 forms have
only reachable sources, 9 have a mix of reachable and stale sources, 121 have
only stale sources, and 393 still lack a source URL. Missing and stale sources
are recorded explicitly rather than silently removed.

## Limitations and next review queue

The current court scopes are observations from a small set of representative
courts. They do not establish statewide availability. Court names should be
resolved to the selected environment's current route key before every audit or
filing.

The next useful step is human review of a small benchmark-linked queue, starting
with CJD 101B, CJD 101A, CJD 109, CJD 102, CJP 27, Vermont divorce forms,
Vermont adult name change, and the general motion forms. Each accepted mapping
should record the reviewer, date, supporting court/form evidence, filing phase,
and any discriminator needed to choose among multiple valid filing names.

## Reproduction

From `benchmarking/promptfoo`:

```bash
npm run normalize-crosswalk
npm run check-crosswalk
npm run audit-crosswalk-live
npm run audit-crosswalk-sources
```

The dated audit artifacts in this directory preserve all results. The live
endpoint is mutable, so a future run should create a new review directory rather
than replace these files.
