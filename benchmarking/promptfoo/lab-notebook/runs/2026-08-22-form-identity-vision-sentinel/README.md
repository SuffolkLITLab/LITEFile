# Form identity vision sentinel

## Outcome

This 24-cell run evaluated the new form-name, form-ID, and form-revision fields
against a flattened MA-01 page and its raster-only scan. It used both extraction
prompt versions and six deployed GPT or Llama vision models.

Twenty cells passed the overall Jaccard threshold, three failed, and one GPT-5.4
nano request returned an API 500. Two Llama 4 Scout v1 responses were prose rather
than parseable JSON.

Among the 21 parseable responses:

- 20 extracted `CJD 101B` correctly.
- 11 matched the complete descriptive form name exactly. Most other name outputs
  returned `Form CJD 101B`, which is an identifier rather than the title.
- Four falsely treated `TEST COPY` or `TEST COPY - NOT FOR FILING` as a revision.
- One scan output `CJ-D 101B`; a deterministic ID matcher should normalize
  punctuation before lookup while retaining the original OCR evidence.

The identifier result supports deterministic lookup. The name and revision
errors led to two targeted prompt-guard iterations preserved as separate runs.

## Prompt-size note

GPT-4o mini reported roughly 26,000 prompt tokens per page image, accounting for
104,727 of the run's 147,922 tokens. Other providers reported far smaller image
token counts. Model comparisons involving vision should therefore keep provider
tokenization and image accounting separate from text-prompt size.

## Artifacts

`inputs/` freezes the exact prompts, renderer, scorer, cases, and page images.
`artifacts/result.json` contains raw Promptfoo output, and `tables/` contains
flat and aggregated results.
