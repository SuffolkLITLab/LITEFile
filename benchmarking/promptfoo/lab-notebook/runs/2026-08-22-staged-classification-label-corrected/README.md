# Staged classification with corrected labels

## Outcome

After the pilot's label audit, the same 84-cell matrix produced 62 exact passes
(73.81%), no API errors, and a mean score of 0.7679. It consumed 135,498 tokens
and recorded approximately $0.1165 in provider-reported cost.

This run corrects two benchmark policies:

- IL-08 accepts the live Eviction category because its `EV` docket prefix and
  caption establish that category, while case type still requires abstention in
  the broader extraction dataset.
- IL-04 accepts either of two live, plausible Tyler contract subtypes and lowers
  label confidence to 0.70.

## Source-fidelity result

First-three-pages source text scored 0.814 with 21 exact passes. Gold evidence
plus source scored 0.786 with 22 passes. Gold evidence alone scored 0.704 with 19
passes. The score/pass distinction comes from partial exact-pair scoring.

The evidence-only condition remains materially weaker. The combined condition
helped filing-type accuracy (6 of 8 versus 5 of 8 for source only), while source
alone was best on case category (8 of 8). This small sample supports carrying
both inputs into the next study rather than reducing the document to a summary.

## Model result

- GPT-5.4 nano: 19 of 21 exact passes
- GPT-5.4: 19 of 21 exact passes
- Mistral Large: 20 of 21 exact passes
- Llama 4 Maverick: 4 of 21 exact passes

Llama frequently returned prose instead of the requested JSON object. That is a
structured-output compatibility issue for this deployment and should not be
treated solely as taxonomy reasoning failure.

## New rendering issue

Three IL-04 outputs selected the correct code and candidate name but copied a
newline or extra spaces inserted when the long authoritative name was serialized
as YAML. Exact comparison correctly rejected the changed name, but the prompt
renderer—not the model—caused the mutation. `prompt_config.py` in this run
freezes the affected renderer. The current renderer uses a wide serialization
width and has a regression test preserving candidate names exactly.

This run supersedes the initial label pilot but is itself followed by a
rendering-corrected baseline.

## Artifacts

`inputs/` includes the corrected label review, live candidate snapshot, generated
cases, prompt catalogs, renderer layers, config, scorer, and fixture builder.
`artifacts/result.json` is raw Promptfoo output. `tables/` contains flat and
aggregated results, including classification level by input mode.
