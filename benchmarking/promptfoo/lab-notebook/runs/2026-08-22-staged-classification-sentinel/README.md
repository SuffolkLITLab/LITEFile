# Staged classification sentinel pilot

## Outcome

This pilot ran 84 cells with no API errors: seven hierarchical decisions, three
source/evidence ablations, and four deployed model families or sizes. It produced
54 exact passes (64.29%) and a mean score of 0.657. The run consumed 134,748
tokens and recorded approximately $0.1325 in provider-reported cost.

The run is preserved primarily because it found two label-design problems:

- IL-08 required abstention even though its `2026-EV` docket prefix and
  landlord-tenant caption support the selectable Eviction category. Eleven of 12
  model/input cells selected Eviction. The current reviewed label now treats that
  selection as correct, but this pilot retains the original label.
- IL-04 required one contract subtype even though both the general
  contract-other and buyer/plaintiff business-dispute paths are live and
  plausible. The current label now accepts both with lower confidence.

Do not use the pilot's aggregate score as the staged baseline. Use the
label-corrected successor run.

## Input-ablation signal

Before correcting labels, first-three-pages source text scored 0.707, evidence
plus source scored 0.693, and gold evidence alone scored 0.571. This does not show
a benefit from replacing source text with the compact evidence pass. It supports
keeping source text available to the classifier and treating extracted evidence
as optional structure.

The sentinel documents are at most a few pages, so this run does not validate a
three-page truncation policy on long filings.

## Model observations

- GPT-5.4 nano was strongest in this pilot: 19 of 21 exact passes, including 7 of
  7 with source text alone.
- Mistral Large passed 17 of 21.
- GPT-5.4 passed 14 of 21.
- Llama 4 Maverick passed 4 of 21. Several responses ignored the JSON-only shape
  and returned commentary, so this deployment needs provider-specific structured
  output handling before its semantic choices can be compared fairly.

## Artifacts

`inputs/` freezes the exact prompt catalog, renderer, config, scorer, candidate
snapshot, generated cases, and fixture builder used by this run. `artifacts/`
contains raw Promptfoo output. `tables/` contains flat result and aggregate files.

The Tyler snapshot is evidence from a changing test endpoint, not permanent legal
truth. Label confidence and review status remain part of each case.
