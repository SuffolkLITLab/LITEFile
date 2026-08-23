# Initial extraction and modality sentinel

This checkpoint asks whether the benchmark discriminates among prompt versions,
model sizes/families, and text-versus-vision input. It evaluates the exact `v1`
production and `v2` evidence-bound definitions preserved in the
[prompt-catalog snapshot](inputs/document_extraction.yaml). The
[manifest](manifest.yaml) records input digests, deployment versions, commands,
and raw artifact names.

## Study design

The text sentinel uses seven documents and six deployed models: matched
small/large pairs from OpenAI, Mistral, and DeepSeek. The modality sentinel uses
the same flattened MA-01 form and a raster-only copy with identical gold data.
Its paired cohort is GPT-5.4 nano/full, GPT-4o mini/full, and Llama 4
Scout/Maverick. Phi-4 Multimodal is recorded as an exploratory vision-only
provider.

Every score is the mean of ordinary field/value-set Jaccard and the
confidence-weighted Jaccard defined by the benchmark scorer. This is not an
inter-annotator agreement coefficient.

This run predates the explicit unordered-party-set scorer snapshot in the
[production-context checkpoint](../2026-08-22-production-context/). Prefer the
newer checkpoint for detailed scoring-semantics comparisons.

## Main results

| Suite | Prompt | Mean score | Passed |
| --- | --- | ---: | ---: |
| Seven-document text | v1 production | 0.526 | 21/42 |
| Seven-document text | v2 evidence-bound | 0.584 | 24/42 |
| Two-document text | v1 production | 0.256 | 4/12 |
| Two-document text | v2 evidence-bound | 0.436 | 6/12 |
| Two-document vision | v1 production | 0.724 | 9/12 |
| Two-document vision | v2 evidence-bound | 0.856 | 12/12 |

The sentinel is discriminating rather than trivially green: the main text run
passed 45/84 calls with a mean score of 0.555. Across that run, v2 improved the
mean by 0.058. The largest prompt-specific change was Mistral Large 3, from
0.310 on v1 to 0.601 on v2. DeepSeek V4 Flash rose from 0.529 to 0.577; other
model pairs were roughly flat or slightly negative, so the prompt effect is not
uniform across families.

Vision produced the strongest practical result. On the raster-only scan, text
input scored 0.000 with 0/12 passes, while rendered-page input scored 0.784 with
11/12 passes. On the text-layer form, vision scored 0.797 versus 0.692 for text.
Across both documents, vision raised the mean from 0.346 to 0.790.

Llama 4 Scout is the clearest prompt interaction: its vision score was 0.000 on
v1 and 1.000 on v2. Maverick was strong with both prompts (1.000 on v1 and 0.929
on v2). That result is worth repeating before treating it as stable.

## Document-level findings

| Text-sentinel case | Mean score | Passed |
| --- | ---: | ---: |
| MA-01 flattened | 0.926 | 12/12 |
| IL-04 flattened | 0.833 | 12/12 |
| VT-06 flattened | 0.698 | 10/12 |
| IL-08 flattened | 0.611 | 11/12 |
| IL-10 motion facsimile | 0.442 | 0/12 |
| MA-01 interactive | 0.335 | 0/12 |
| MA-01 scanned | 0.039 | 0/12 |

The interactive/flattened pair exposes an input-layer problem: Promptfoo's PDF
parser omitted AcroForm values from the interactive form but recovered them
after flattening. The raster scan has one byte of extractable text by design.
These failures are useful evidence, but they do not isolate prompt quality.

IL-10 also shows that the current value matcher is stricter than a human legal
reviewer. Equivalent court names with different word order, role descriptions,
and near-matches such as “Administration of a decedent's estate” versus the
exact Tyler label all lose credit. Exact Tyler labels should remain strict, but
ordinary document facts need more deliberate canonicalization.

## Experimental Phi result

Phi-4 Multimodal completed three of four 180-DPI vision calls. Its one API error
reported 5,626 input tokens against a 4,096-token context limit. A subsequent
empty-text scan request stalled at the gateway, so Phi was excluded from the
paired text cohort. The final renderer uses 140 DPI, and Phi remains in the
vision config as an explicitly experimental provider.

## Limitations and next decisions

- This is one run per cell on seven synthetic documents, not an uncertainty
  estimate. Repeat high-leverage cells before ranking close models.
- Promptfoo's `pdf-parse` text is not production parity with LITEFile's file
  upload and MarkItDown fallback. A custom provider should exercise those exact
  paths next.
- In the current development environment, MarkItDown raises its missing PDF
  dependency error on these files. Production-fallback parity therefore needs a
  dependency/test fix before its extraction scores can be trusted.
- The modality comparison uses one one-page form. Add multi-page, rotated,
  low-contrast, handwriting, and checkbox-heavy scans.
- Gold labels with 0.65 confidence should not drive prompt changes until the
  Tyler path is verified or the uncertainty is explicitly modeled.
- Improve value canonicalization separately from prompt iteration, then preserve
  this run as the pre-change baseline.

Machine-readable details are in
[`scores_by_model_prompt.csv`](tables/scores_by_model_prompt.csv),
[`scores_by_case.csv`](tables/scores_by_case.csv), and
[`field_outcomes.csv`](tables/field_outcomes.csv). Raw Promptfoo JSON is gzip
compressed under `artifacts/`.
