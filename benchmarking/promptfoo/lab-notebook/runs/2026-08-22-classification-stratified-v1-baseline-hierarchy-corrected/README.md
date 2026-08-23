# Valid two-stage evidence-plus-source baseline

## Result

31/36 selections passed (86.11%), with 0 API errors.
The run used 67,877 total tokens.

This run is valid for the corrected comparison. Baseline for the corrected stratified matrix.

## Failures

| Model | Case | Level | Score |
| --- | --- | --- | ---: |
| mistral-large:mistral-large-3 | MA-01 | case category | 0.3 |
| openai-small:gpt-5.4-nano | VT-03 | filing type | 0.3 |
| openai-small:gpt-5.4-nano | VT-06 | filing type | 0 |
| openai-small:gpt-5.4-nano | IL-02 | filing type | 0.3 |
| openai-small:gpt-5.4-nano | IL-08 | case category | 0 |

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
