# Court-document extraction study

This directory evaluates LITEFile's versioned document-extraction prompts as a
Promptfoo prompt × model × document matrix.

The checked-in dataset has 66 PDF cases:

- 30 interactive PDFs
- the same 30 forms flattened to simulate print-to-PDF or scanned workflows
- 6 standalone motion facsimiles that emphasize abstention

The two prompts come from the application-owned
[`document_extraction.yaml`](../../efile_app/efile/prompts/document_extraction.yaml), not
from benchmark-only copies. The default text matrix compares the production
`v1` prompt and the evidence-bound `v2` candidate across matched small/large
OpenAI, Mistral, and DeepSeek deployments (792 calls for a full run).

The seven-document sentinel covers a common initiating filing, an
interactive/flattened pair, a Tyler-verified classification, an ambiguous Tyler
classification, an abstention case, a motion with limited supported inference,
and an image-only scan. The two-document modality sentinel isolates a
text-layer PDF and a raster-only copy with identical expected results.

## Install and validate

```bash
cd benchmarking/promptfoo
npm install
npm run check-cases
npm run prepare-sentinel
npm run check-inputs
PROMPTFOO_CONFIG_DIR=.promptfoo PROMPTFOO_DISABLE_WAL_MODE=true npm run smoke
PROMPTFOO_CONFIG_DIR=.promptfoo PROMPTFOO_DISABLE_WAL_MODE=true \
  promptfoo validate -c promptfooconfig.yaml
```

PDF variables require Promptfoo's `pdf-parse` peer dependency, which is listed
in `package.json`.

Promptfoo currently brings optional local-model packages that produce five high
severity `npm audit` findings in `sharp`/`libvips` and `adm-zip`. This study does
not use those packages; `npm audit --omit=optional` is clean. Do not process
untrusted local-model archives through the optional stack until upstream fixes
are available.

## Run the matrix

Set `OPENAI_API_KEY` and, for an OpenAI-compatible gateway, `OPENAI_BASE_URL`.
Then run:

```bash
PROMPTFOO_CONFIG_DIR=.promptfoo PROMPTFOO_DISABLE_WAL_MODE=true npm run eval
PROMPTFOO_CONFIG_DIR=.promptfoo PROMPTFOO_DISABLE_WAL_MODE=true npm run view
```

Promptfoo extracts text from each PDF with its own PDF parser before rendering
the text prompt. This is a provider-neutral text-input comparison, but it is not
production parity with LITEFile's provider file upload or MarkItDown fallback.
The separate modality suite renders pages to images for vision-capable models.

For a quick diagnostic study, run:

```bash
npm run eval-sentinel -- --env-file ../../efile_app/.env --no-cache
npm run eval-modality-text -- --env-file ../../efile_app/.env --no-cache
npm run eval-modality-vision -- --env-file ../../efile_app/.env --no-cache
```

The modality configs use the same deployed GPT-5.4, GPT-4o, and Llama 4 models
on extracted text and rendered-page input. Phi-4 Multimodal remains in the
vision config as an experimental extra; its 4,096-token context and low
deployment capacity make it unsuitable for the empty-text side of the paired
test.

For the production-like preprocessing comparison, run:

```bash
npm run eval-production-context -- --env-file ../../efile_app/.env --no-cache
```

`data/document_inputs.json` is a deterministic preprocessing corpus. It records
the source PDF hash, pre-run MarkItDown text, non-empty AcroForm values from
pypdf, and exact parser versions. Rebuild it with `npm run prepare-sentinel`.
The production-context config compares MarkItDown alone, MarkItDown plus form
fields, and rendered-page vision plus both machine-readable sources.

## Staged classification sentinel

The proposed staged flow has two application-owned prompt catalogs:

- [`document_evidence_extraction.yaml`](../../efile_app/efile/prompts/document_evidence_extraction.yaml)
  extracts direct facts and short classification clues without inventing Tyler
  labels.
- [`efile_taxonomy_classification.yaml`](../../efile_app/efile/prompts/efile_taxonomy_classification.yaml)
  selects category, then case type, then filing type from candidates constrained
  by the court and earlier selections.

The original classification ablation compares source text only, extracted
evidence only, and extracted evidence plus source text. The current stratified
study uses evidence plus the first three source pages and compares two-stage and
three-stage classification strategies over 18 decisions. Source input records
whether later pages were omitted, making summary loss measurable instead of
assuming that the first pass is sufficient.

The extraction gold labels also include the printed form name, form identifier,
and separately parsed revision for every synthetic document. The current prompts
tell vision models to inspect headers, footers, and margins and distinguish a
descriptive form name from a `Form <ID>` label. The staged evidence prompt also
asks for a one-sentence, evidence-grounded form purpose; that semantic field is
not yet part of the exact Jaccard gold labels.

Refresh the small live-taxonomy snapshot and run the ablation with:

```bash
npm run refresh-classification-sentinel
npm run check-classification-sentinel
npm run eval-classification-sentinel -- --env-file ../../efile_app/.env --no-cache
```

Run the current best experimental response design with:

```bash
npm run eval-classification-reference-form-crosswalk -- \
  --env-file ../../efile_app/.env --no-cache
```

It asks the model to choose a short run-local candidate reference. Application
code resolves that reference to the exact catalog name and current route key,
so the model never has to reproduce a punctuation-sensitive taxonomy string.
See the [stratified classification study](lab-notebook/studies/2026-08-22-stratified-classification/)
for the full independent-run comparison.

The snapshot records its endpoint, retrieval time, court, hierarchy parents,
and exact candidate lists. Refreshing it is an explicit network operation so a
changing Tyler test catalog does not silently change an old run.

See the [official form-to-code crosswalk plan](lab-notebook/design/form-code-crosswalk.md)
for the proposed precision-first form registry, one-to-many mappings, live-code
audits, and deterministic-lookup evaluation.

The crosswalk stores Tyler category, case-type, filing-type, and court names as
the durable identifiers. Numeric taxonomy keys and court route keys may differ
between environments and are retained only as dated observation provenance.
At runtime, resolve the recorded names against the selected environment and
court instead of reusing a captured numeric key.

Crosswalk status has two independent dimensions:

- `catalog_status` says whether the complete named hierarchy is currently
  selectable, only partially observed, not current, or not checked.
- `association_status` says whether the mapping is merely a generated
  suggestion or has been confirmed by a human as correct for the form.

`catalog_status: current` does not make a mapping safe for deterministic use.
Only `association_status: human_verified` does, and the selected court must
still publish the names when the filing is created. Normalize and structurally
check the data with `npm run check-crosswalk`. Use `npm run
audit-crosswalk-live` for a name-based hierarchy check and `npm run
audit-crosswalk-sources` to check form source links.

## Lab notebook

Store durable evaluation records under `lab-notebook/runs/`. Each run preserves
raw Promptfoo output, input snapshots and digests, flat result/field CSVs, and a
short narrative tied to exact prompt versions. See
[`lab-notebook/README.md`](lab-notebook/README.md) for the convention.

## Labels and confidence

`data/cases.jsonl` is generated from the synthetic corpus and contains the PDF
reference, expected field/value sets, abstention targets, and per-field label
confidence. Rebuild it after changing the corpus or reviews:

```bash
npm run build-cases
```

`data/tyler_label_reviews.json` records live checks against
`https://efile-test.suffolklitlab.org` as of the review date. A label can be:

- `synthetic_document_ground_truth`: directly visible synthetic content
- `verified_live`: an exact selectable Tyler label observed at the reviewed
  hierarchy
- `verified_live_crosswalk_supported`: a current name also supported by an exact
  form crosswalk match
- `verified_live_form_supported`: a current name supported by the printed form
  identity
- `verified_live_document_supported`: a current name whose qualifier or amount
  is directly supported by the document
- `verified_live_generic_filing_label`: a generic current Tyler filing name kept
  separate from the exact printed form title
- `verified_live_ambiguous`: selectable, but more than one legal or procedural
  interpretation remains plausible
- `synthetic_semantic_label_unverified`: a reasonable semantic label not yet
  verified for that court
- `document_does_not_establish`: the model should omit the field
- `rejected_by_live_catalog`: the original broad label is not selectable on the
  tested court path
- `crosswalk_conflict_unresolved`: neither the crosswalk nor current hierarchy
  establishes a safe exact label, so the benchmark requires abstention

The live endpoint is a moving test catalog. Exact normalized names are the
durable identities. Numeric keys are useful dated audit and routing evidence,
not permanent legal truth.

Refresh the live check without changing the labels:

```bash
npm run audit-labels
```

## Scoring

`assertions/set_jaccard.js` normalizes common key aliases and compares the set of
correct field/value pairs with the predicted set. JSON field order is ignored.
Scalar values retain word order, while the plaintiff, defendant, and other-party
fields compare their members as unordered sets. A wrong value contributes both
a false positive and a false negative; an unsupported abstention field is a
false positive. Allowed optional inferences are neutral.

The reported score averages ordinary Jaccard similarity with a
confidence-weighted Jaccard score. Promptfoo also shows field-level component
results so a strong score cannot hide a systematic failure such as hallucinating
case types on motions.

Jaccard similarity is the relevant set metric here. If inter-annotator agreement
becomes part of label creation, add a separate agreement statistic such as
Krippendorff's alpha; it answers a different question.

The taxonomy-classification scorer is intentionally different: it checks the
hierarchical status and exact durable Tyler name selected from that run's dated
catalog snapshot. It then checks response integrity by resolving either the
model's short selection reference or returned route key against the offered
candidate. The numeric key is not part of gold identity. Set Jaccard would give
partial credit to a result that is not actually selectable in the required court
path.
