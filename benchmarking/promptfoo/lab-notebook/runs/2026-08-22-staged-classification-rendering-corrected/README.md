# Staged classification rendering-corrected baseline

## Outcome

This is the first staged sentinel with both audited gold labels and exact,
non-wrapping serialization of authoritative Tyler candidate names. The 84-cell
matrix produced 62 exact passes (73.81%), no API errors, and a mean score of
0.743. It consumed 135,557 tokens and recorded approximately $0.1198 in
provider-reported cost.

The raw aggregate is strongly affected by Llama 4 Maverick's structured-output
failures. Among GPT-5.4 nano, GPT-5.4, and Mistral Large, the results were:

- evidence plus source: 21 of 21 exact
- source only: 19 of 21 exact
- evidence only: 18 of 21 exact

This is the clearest current result: compact evidence is not a safe replacement
for document text, while adding it alongside the source eliminated all semantic
selection failures for the three JSON-compatible deployments in this small set.

## Hierarchy observations

Across all four models, source text alone was strongest for case category (8 of
8). Evidence plus source produced 9 of 12 case-type passes and 6 of 8 filing-type
passes. Evidence alone was weakest on filing type (4 of 8), which is consistent
with a summary dropping the distinction between the document being filed and a
document merely mentioned in its requested relief.

The largest candidate node had 160 filing types. In one source-only failure,
Mistral selected `Inventory` for a motion seeking more time to file an inventory;
the combined evidence condition correctly selected `Motion`. That is a useful
example of pass-one structure helping when the full text contains a salient but
misleading noun.

## Model observations

- Mistral Large: 20 of 21 exact passes
- GPT-5.4 nano: 19 of 21 exact passes
- GPT-5.4: 19 of 21 exact passes
- Llama 4 Maverick: 4 of 21 exact passes

Llama frequently returned prose instead of the requested JSON shape. A follow-up
should test an enforced provider response format or a provider-specific adapter
before comparing its classification quality.

## Limits and next study

The pass-one evidence in this sentinel is gold synthetic evidence. The next
end-to-end experiment should feed actual outputs from
`document-evidence-extraction:v1`, while retaining the oracle-evidence arm to
separate extraction error from classification error.

All source documents here fit within three pages. Add long, realistic filings
with classification-changing evidence after page three before adopting a hard
production cutoff. Also exercise `request_more_candidates` with deliberately
short candidate lists and score retrieval success and loop count.

## Artifacts

`inputs/` freezes the reviewed labels, live candidate snapshot, generated cases,
both prompt catalogs, both renderer layers, config, scorer, and fixture builder.
`artifacts/result.json` is raw Promptfoo output. `tables/` contains flat and
aggregated results, including classification level by input mode.
