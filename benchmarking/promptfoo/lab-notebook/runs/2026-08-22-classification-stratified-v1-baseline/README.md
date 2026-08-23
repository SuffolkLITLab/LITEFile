# Initial two-stage baseline

## Result

32/36 selections passed (88.89%), with 0 API errors.
The run used 68,385 total tokens.

This run is diagnostic only and is excluded from the final comparison. The evaluated parent context leaked the target value at the level being classified.

## Failures

| Model | Case | Level | Score |
| --- | --- | --- | ---: |
| openai-small:gpt-5.4-nano | MA-01 | case category | 0.2 |
| mistral-large:mistral-large-3 | MA-01 | case category | 0 |
| openai-small:gpt-5.4-nano | VT-03 | filing type | 0.3 |
| openai-small:gpt-5.4-nano | IL-02 | filing type | 0.3 |

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
