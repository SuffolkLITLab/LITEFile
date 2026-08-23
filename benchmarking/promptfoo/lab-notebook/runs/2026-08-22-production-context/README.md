# Production-like PDF context comparison

This checkpoint tests three complementary inputs from the same MA-01 document:
MarkItDown text, MarkItDown plus AcroForm values, and a rendered page plus both
machine-readable sources. It crosses those inputs with the exact `v1`
production and `v2` evidence-bound prompt snapshots and six vision-capable
models. See the [manifest](manifest.yaml) for deployment versions, commands, and
digests.

## Input construction

The deterministic [preprocessing snapshot](inputs/build_document_inputs.py)
uses the same MarkItDown package declared by LITEFile and pypdf's `get_fields()`.
The resulting [document-input corpus](inputs/document_inputs.json) records source
PDF hashes, tool versions, precomputed text, and non-empty form-field values.

| MA-01 variant | MarkItDown characters | Non-empty form fields | Rendered page |
| --- | ---: | ---: | ---: |
| Interactive | 507 | 16 | Yes |
| Flattened | 916 | 0 | Yes |
| Raster-only scan | 0 | 0 | Yes |

This is the desired diagnostic structure: fields can rescue the interactive
form, text can handle the flattened form, and only vision can handle the scan.

## Scoring semantics

The [scorer snapshot](inputs/set_jaccard.js) treats extracted fields as a set, so
JSON key order is irrelevant. Words inside scalar values remain ordered: a
court-name word shuffle is not silently accepted. Plaintiff, defendant, and
other-party collections are themselves unordered sets, so `A; B` and `[B, A]`
match while a missing party does not.

This scorer is newer than the initial sentinel's scorer. Use comparisons within
this run rather than treating small score changes from the previous notebook as
prompt effects.

## Results by input and prompt

| Input mode | v1 mean | v1 passed | v2 mean | v2 passed |
| --- | ---: | ---: | ---: | ---: |
| MarkItDown | 0.245 | 4/18 | 0.404 | 6/18 |
| MarkItDown + form fields | 0.333 | 7/18 | 0.592 | 12/18 |
| Vision + MarkItDown + fields | 0.725 | 15/18 | 0.910 | 18/18 |

Form fields have the intended targeted effect. On the interactive form they
raise the mean from 0.273 to 0.683 and passes from 0/12 to 9/12. With v2 alone,
the change is 0.369 to 0.926 and 0/6 to 6/6. They have essentially no effect on
the flattened form because its values are already in the text layer.

The scan remains 0.000 for both text modes. Vision plus context scores 0.786 on
the scan with 11/12 passes; v2 scores 0.878 and passes all six models. Across all
three variants, v2 vision plus context passes 18/18 calls with a 0.910 mean.

## Model and prompt interactions

Llama 4 Scout again shows a sharp prompt dependency: its vision/context score
is 0.000 for v1 and 1.000 for v2. Llama 4 Maverick moves the other direction but
remains strong, from 1.000 on v1 to 0.906 on v2. The OpenAI vision models pass
every cell; GPT-4o reaches 1.000 with v2, while GPT-5.4 is stable at 0.837 for
both prompts.

The general conclusion is not merely “use vision.” Structured form values are a
cheap and effective bridge for interactive PDFs, text is sufficient for many
flattened PDFs, and vision is the necessary fallback when both sources are
empty. Input detection can therefore select a tier rather than sending every
document through the most expensive path.

## Production implications

- Pre-extract AcroForm values before invoking the model and include them with
  MarkItDown text on the fallback path.
- Treat zero text plus zero form values as a strong signal to invoke vision or
  OCR.
- Preserve the v2 evidence rules when supplying structured context; v2 gains are
  largest on the sources that otherwise require inference.
- Add this hybrid context path to the actual LITEFile provider call before
  claiming full production parity. The current vision test uses rendered page
  images, not the provider Files API.
- Add adversarial form-field values to a later security sentinel and explicitly
  delimit extracted content as untrusted data.

## Limitations

- This is one synthetic, one-page form in three representations, with one run
  per cell.
- Vision uses a 140-DPI rendered PNG. Provider-native PDF ingestion may differ.
- Form field names in the synthetic corpus are unusually descriptive; real
  court PDFs often use opaque identifiers.
- No OCR engine was tested on the raster-only PDF.

Machine-readable results are in
[`scores_by_input_mode.csv`](tables/scores_by_input_mode.csv),
[`scores_by_document_input.csv`](tables/scores_by_document_input.csv),
[`scores_by_model_prompt.csv`](tables/scores_by_model_prompt.csv), and
[`field_outcomes.csv`](tables/field_outcomes.csv). The full Promptfoo result is
gzip-compressed under `artifacts/`.
