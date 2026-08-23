# Staged court-filing classification

## Study question

Can LITEFile improve exact court-code selection by separating direct evidence
extraction from court-specific taxonomy classification without losing useful
information from the source filing?

This design treats an evidence summary as an enhancement and index, not as a
replacement for the document. The classifier receives the first three pages of
MarkItDown text by default because a filing's identity is normally established
near its beginning. The pipeline must record whether later pages were omitted so
that this assumption can be tested on longer documents.

## Proposed stages

| Stage | Input | Output | Evaluation |
| --- | --- | --- | --- |
| Direct evidence | PDF or MarkItDown text plus AcroForm values | Printed facts and short classification excerpts, but no Tyler labels | Field/value Jaccard and field-level recall |
| Case category | Court, filing phase, evidence, source excerpt, valid court categories | Candidate reference, abstention, or request for more candidates | Exact durable name and status after reference resolution |
| Case type | The selected category plus the same source inputs and valid child types | Candidate reference, abstention, or request for more candidates | Exact durable name and status after reference resolution |
| Filing type | The selected category and case type plus the same source inputs and valid filing types | Candidate reference, abstention, or request for more candidates | Exact durable name and status after reference resolution |

Before taxonomy classification, LITEFile should attempt the deterministic
official-form lookup described in
[`form-code-crosswalk.md`](form-code-crosswalk.md). A unique, currently valid and
human-verified form mapping can bypass model classification. Until associations
are human-verified, exact-form matches are retrieval hints whose hierarchy must
be confirmed against the source.

The application prompt sources are:

- `efile_app/efile/prompts/document_evidence_extraction.yaml`, version `v1`
- `efile_app/efile/prompts/efile_taxonomy_classification.yaml`, version `v1`

The existing `document_extraction.yaml` remains the production single-pass
baseline until this staged flow has enough evidence to replace it.

## Source-fidelity ablation

`promptfooconfig.classification-sentinel.yaml` evaluates three versions of the
same classifier prompt and candidate lists:

1. First-three-pages source text only
2. Extracted direct evidence only
3. Extracted direct evidence plus first-three-pages source text

The current evidence is gold synthetic evidence. That isolates classification
quality from pass-one model errors. A later end-to-end run should replace it with
actual pass-one output and report both oracle-evidence and predicted-evidence
results.

The synthetic sentinel documents are short, so the first-three-pages input is
usually the complete source. Add longer documents whose key qualifier occurs
after page three before deciding that the cutoff is safe in production.

## Candidate retrieval and retry loop

Candidate retrieval must follow the Tyler hierarchy and the selected court:

1. Retrieve fileable categories for the court and filing phase.
2. Select a category or ask for another candidate search.
3. Retrieve case types under the selected category.
4. Select a case type, abstain, or ask for another candidate search.
5. Retrieve filing types under the selected category and case type.
6. Select a filing type, abstain, or ask for another candidate search.

The prompt may return `request_more_candidates` with grounded search terms. The
host application—not the model—must query the authoritative endpoint and append
only valid results. It should stop after the prompt catalog's configured maximum
rounds and ask the filer when no defensible match exists. A model must never
invent a Tyler code. Prefer short run-local candidate references and let the host
resolve exact names and current route keys.

The first stratified study found that a top-12 lexical shortlist retained the
gold candidate in every case but reduced accuracy. A retry design must preserve
close contrast candidates and measure more than gold recall before it replaces
the full candidate list.

A downstream dependency can make a later level unreachable. For example, when a
generic fee-waiver document does not establish case type, LITEFile may be unable
to retrieve the correct filing-type list until it gets case context from the
user or an existing docket. That is a workflow limitation, not a prompt failure.

## Reproducibility

`data/classification_taxonomy_snapshot.json` records the live endpoint,
retrieval time, hierarchy parents, candidate URLs, candidate lists, reviewed
label confidence, and exact expected durable name. The generated
`data/classification_sentinel_cases.jsonl` binds those candidates to a frozen
document preprocessing record.

Refresh snapshots explicitly. Completed run directories must copy the snapshot,
generated cases, both prompt YAML files, the Promptfoo config and renderer, the
scorer, raw output, flat summaries, and a narrative. Never refresh a completed
run in place.

## Initial interpretation rules

- Compare exact-name selection accuracy and abstention separately for each hierarchy
  level.
- Report results by input ablation and model; an overall average can hide a bad
  case-type stage.
- Treat `request_more_candidates` as neither an exact selection nor a
  hallucination. Track whether the requested query eventually retrieves the gold
  value and how many rounds it takes.
- Keep label confidence next to each result. Ambiguous Tyler labels should not be
  presented as definitive ground truth.
- Add an end-to-end metric only after pass-one predicted evidence and candidate
  retrieval are connected. Report invalid hierarchy combinations as a separate
  hard failure.
