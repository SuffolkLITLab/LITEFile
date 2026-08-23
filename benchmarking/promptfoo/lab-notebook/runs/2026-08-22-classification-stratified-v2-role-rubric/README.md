# Initial role-rubric variation

## Result

36/36 selections passed (100.00%), with 0 API errors.
The run used 73,576 total tokens.

This run is diagnostic only and is excluded from the final comparison. The evaluated parent context leaked the target value at the level being classified.

## Failures

No scored failures.

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
