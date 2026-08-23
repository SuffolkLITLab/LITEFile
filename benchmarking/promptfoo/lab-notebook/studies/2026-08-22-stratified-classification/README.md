# Stratified staged-classification study

## Result

The strongest tested design was not to ask the model to reproduce a Tyler name or
numeric key. It assigned a short run-local reference to each live candidate, asked
the model to select the reference, and let application code recover the exact name
and current route key. That variation passed all 36 model/decision cells.

| Variation | Stages | Passes | Accuracy | Prompt tokens |
| --- | ---: | ---: | ---: | ---: |
| Evidence + source baseline | 2 | 31/36 | 86.11% | 61,330 |
| Role rubric | 2 | 33/36 | 91.67% | 65,830 |
| Exact-form crosswalk | 3 | 34/36 | 94.44% | 69,908 |
| Crosswalk + top-12 Python retrieval | 3 | 31/36 | 86.11% | 45,578 |
| Crosswalk + canonical-copy guard | 3 | 33/36 | 91.67% | 73,994 |
| Crosswalk + application-resolved reference | 3 | 36/36 | 100.00% | 72,895 |

Each row is an independent Promptfoo run over the same hierarchy-corrected
sentinel: 18 decisions × two deployed models (`gpt-5.4-nano` and
`mistral-large-3`). The sample contains six decisions per jurisdiction across
Massachusetts, Vermont, and Illinois. It includes four category, six case-type,
and eight filing-type decisions.

## What changed accuracy

The role rubric helped `gpt-5.4-nano`, which rose from 14/18 on the baseline to
18/18 with either the role rubric or crosswalk context. Mistral was already 17/18
on the baseline, but sometimes inferred `stipulated` without evidence and twice
rewrote the exact Vermont small-claims name's amount punctuation.

Exact-form crosswalk context was the best ordinary code/name prompt (34/36). It
fixed both category errors seen in the baseline and improved filing selection,
but it did not resolve the weak Vermont contested/stipulated distinction. It also
increased prompt tokens by 14.0% over baseline.

The top-12 retrieval experiment reduced prompt tokens by 25.7% and retained the
gold candidate in every cell, yet accuracy fell back to 31/36. Candidate recall is
therefore not a sufficient retrieval metric: removing plausible contrast choices
changed classification behavior. This shortlist should not replace the full list
without an iterative fallback and a contrast-preservation test.

Adding more instructions to copy canonical strings did not solve Mistral's string
rewriting. A run-local `C###` reference did: both models selected 18/18 references,
and Python could then return the exact candidate name and current route key. This
also enforces the rule that numeric Tyler keys are never stored as durable gold.

## Errors worth keeping in the sentinel

- MA-01 distinguishes an individual 1B complaint (`Domestic Relations`) from a
  joint 1A petition. Mistral selected the joint category in two ordinary prompts.
- VT-01 distinguishes contested from stipulated dissolution. The document does
  not say stipulated, but this label still deserves court-facing review.
- VT-03 has different amount formatting and ranges at the case-type and
  filing-type levels. Models sometimes copied or reconstructed the wrong string.
- IL-02 offers both generic `Petition` and the specific dissolution petition.
- IL-08 is a generic fee-waiver document whose underlying Eviction category is
  inferred from the docket. In production, existing-case metadata should usually
  supply that category instead of asking the model to rediscover it.

## Limits of this result

- The evidence stage uses reviewed synthetic evidence, not actual pass-one model
  output. The run measures classification conditional on a good first pass.
- Each hierarchy level receives reviewed parent selections. Cascade errors and
  retry behavior are not measured.
- This is 18 synthetic decisions, two models, and one run per variation. A
  36/36 sentinel result is evidence that the harness and design are useful, not
  an estimate of production accuracy.
- The documents use MarkItDown text rather than vision, and most are short.
- Crosswalk associations and several taxonomy labels still need court-facing
  review; label confidence remains part of every case record.

## Most promising directions

1. Use application-resolved candidate references in the second-pass response
   schema. Persist the exact canonical name; use the current route key only for
   the active e-filing session.
2. Keep full candidate lists until retrieval supports a real fallback: retrieve a
   batch, let the classifier request another batch, and preserve close contrast
   candidates and qualifier variants.
3. Gate crosswalk hints to exact form matches whose hierarchy is current, then
   prioritize human review of the association itself. The current crosswalk is
   useful retrieval evidence, not gold.
4. Pass existing case metadata for subsequent filings. Generic motions, answers,
   and fee-waiver forms often cannot establish the underlying category/type from
   their own text.
5. Run an end-to-end hierarchy study where predicted parents, retry requests, and
   abstentions propagate. This sentinel isolates levels using reviewed parents,
   so it does not measure cascade errors yet.
6. Have court-facing reviewers adjudicate the remaining low-confidence choices,
   especially Vermont contested/stipulated paths and Illinois local usage.

The exact comparison data is in
[`run-comparison.csv`](run-comparison.csv). The first four rows are diagnostic
runs with a discovered parent-context leak; they remain recorded but are excluded
from the table above and all conclusions.
