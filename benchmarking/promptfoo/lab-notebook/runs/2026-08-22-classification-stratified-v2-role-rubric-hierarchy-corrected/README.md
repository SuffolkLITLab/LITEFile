# Two-stage variation with explicit category/type/filing distinctions

## Result

33/36 selections passed (91.67%), with 0 API errors.
The run used 73,021 total tokens.

This run is valid for the corrected comparison. Improved overall accuracy, but hurt one Vermont case-type decision.

## Failures

| Model | Case | Level | Score |
| --- | --- | --- | ---: |
| mistral-large:mistral-large-3 | MA-01 | case category | 0.3 |
| mistral-large:mistral-large-3 | VT-01 | case type | 0.3 |
| mistral-large:mistral-large-3 | VT-03 | filing type | 0.2 |

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
