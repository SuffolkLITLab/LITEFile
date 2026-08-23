# Initial exact-form crosswalk variation

## Result

35/36 selections passed (97.22%), with 0 API errors.
The run used 77,717 total tokens.

This run is diagnostic only and is excluded from the final comparison. The evaluated parent context leaked the target value at the level being classified.

## Failures

| Model | Case | Level | Score |
| --- | --- | --- | ---: |
| mistral-large:mistral-large-3 | VT-03 | filing type | 0.2 |

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
