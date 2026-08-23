# Extraction benchmark lab notebook

Each directory under `runs/` is an immutable record of one study checkpoint. A
run contains:

- a narrative `README.md` with findings and limitations
- `manifest.yaml` with prompt versions, source revision, model deployments,
  commands, and SHA-256 input digests
- raw Promptfoo JSON under `artifacts/`
- snapshots of the prompt catalog and evaluated configs under `inputs/`
- flat CSV and JSON summaries under `tables/`

Create a new run directory instead of replacing an earlier run. Keep generated
page images only when they materially define the experiment, such as a
text-versus-vision comparison. API keys and `.env` files must never be copied
into the notebook.

Use `scripts/summarize_run.py` to make consistent tables from raw results:

```bash
python scripts/summarize_run.py \
  --output lab-notebook/runs/RUN_ID/tables \
  suite-name=lab-notebook/runs/RUN_ID/artifacts/result.json
```

Design notes that span several runs live under `design/`. The current staged
classification plan and source-versus-summary ablation are recorded in
[`design/staged-classification.md`](design/staged-classification.md).
The proposed deterministic official-form registry and one-to-many Tyler
crosswalk process are recorded in
[`design/form-code-crosswalk.md`](design/form-code-crosswalk.md).

Dataset reviews that are not model evaluations live under `reviews/`. They use
the same immutable-artifact approach and record structural checks, live catalog
audits, source checks, and cleanup decisions. See the
[`2026-08-22 form crosswalk cleanup review`](reviews/2026-08-22-form-crosswalk-cleanup/)
for the first crosswalk checkpoint.

Cross-run syntheses live under `studies/`. The current findings and recommended
production direction are in the
[`2026-08-22 stratified staged-classification study`](studies/2026-08-22-stratified-classification/).
The implementation and real-upload verification of that direction are recorded
in the
[`2026-08-23 production staged-classification study`](studies/2026-08-23-production-staged-classification/).

## Runs

| Run | Purpose |
| --- | --- |
| [2026-08-22 sentinel baseline](runs/2026-08-22-sentinel-baseline/) | Initial prompt/model and text/vision sentinel |
| [2026-08-22 production context](runs/2026-08-22-production-context/) | MarkItDown, AcroForm, and hybrid vision comparison |
| [2026-08-22 staged classification sentinel](runs/2026-08-22-staged-classification-sentinel/) | Pilot source/evidence ablation that exposed two gold-label issues |
| [2026-08-22 staged classification with corrected labels](runs/2026-08-22-staged-classification-label-corrected/) | Corrected gold labels; exposed YAML wrapping of long authoritative names |
| [2026-08-22 staged classification rendering-corrected](runs/2026-08-22-staged-classification-rendering-corrected/) | Current staged baseline; audited labels and exact candidate serialization |
| [2026-08-22 form identity vision sentinel](runs/2026-08-22-form-identity-vision-sentinel/) | Initial form-name/ID vision study; exposed false revision and name/ID confusion |
| [2026-08-22 form revision guard](runs/2026-08-22-form-revision-guard/) | First revision guard; GPT-4o mini still treated `TEST COPY` as a revision |
| [2026-08-22 form identity guard v2](runs/2026-08-22-form-identity-guard-v2/) | Current focused form identity checkpoint; 8/8 exact behavior on flattened and scanned MA-01 |
| [2026-08-22 classification baseline, hierarchy-corrected](runs/2026-08-22-classification-stratified-v1-baseline-hierarchy-corrected/) | Valid 18-decision, two-model staged baseline |
| [2026-08-22 classification role rubric, hierarchy-corrected](runs/2026-08-22-classification-stratified-v2-role-rubric-hierarchy-corrected/) | Explicit category/type/filing role distinctions |
| [2026-08-22 classification form crosswalk, hierarchy-corrected](runs/2026-08-22-classification-stratified-v2-form-crosswalk-hierarchy-corrected/) | Exact-form retrieval context with full candidate lists |
| [2026-08-22 classification retrieval shortlist, hierarchy-corrected](runs/2026-08-22-classification-stratified-v3-retrieval-shortlist-hierarchy-corrected/) | Python top-12 retrieval and token/accuracy tradeoff |
| [2026-08-22 guarded form crosswalk](runs/2026-08-22-classification-stratified-v3-guarded-form-crosswalk/) | Canonical-copy and qualifier guard experiment |
| [2026-08-22 application-resolved references](runs/2026-08-22-classification-stratified-v4-reference-form-crosswalk/) | Best current result: 36/36 using run-local candidate references |
