# Three-stage variation with a Python top-12 candidate shortlist

## Result

31/36 selections passed (86.11%), with 0 API errors.
The run used 52,979 total tokens.

This run is valid for the corrected comparison. Reduced prompt tokens but also removed useful contrast candidates.

## Failures

| Model | Case | Level | Score |
| --- | --- | --- | ---: |
| mistral-large:mistral-large-3 | VT-01 | case type | 0.3 |
| openai-small:gpt-5.4-nano | VT-03 | case type | 0.3 |
| openai-small:gpt-5.4-nano | IL-02 | filing type | 0.3 |
| mistral-large:mistral-large-3 | IL-04 | case type | 0.3 |
| openai-small:gpt-5.4-nano | IL-08 | case category | 0 |

## Reproduction record

The `inputs/` directory contains the exact cases reconstructed from the raw Promptfoo result,
the evaluated config, renderer, scorer, live-catalog snapshot, reviewed labels, and builder.
`artifacts/result.json` is the raw Promptfoo output; stable aggregate tables are under `tables/`.
Numeric Tyler values in the snapshot are dated route-key observations, not gold identities.
The assertion scores the exact durable name and checks the returned route key or run-local
selection reference against the offered candidate.
