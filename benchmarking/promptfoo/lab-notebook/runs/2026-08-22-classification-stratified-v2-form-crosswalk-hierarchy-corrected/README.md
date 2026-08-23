# Three-stage variation with deterministic exact-form retrieval

## Result

34/36 selections passed (94.44%), with 0 API errors.
The run used 77,335 total tokens.

This run is valid for the corrected comparison. Best ordinary code/name response run; crosswalk suggestions remained explicitly unverified.

## Failures

| Model | Case | Level | Score |
| --- | --- | --- | ---: |
| mistral-large:mistral-large-3 | VT-01 | case type | 0.3 |
| mistral-large:mistral-large-3 | VT-03 | filing type | 0.2 |

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
