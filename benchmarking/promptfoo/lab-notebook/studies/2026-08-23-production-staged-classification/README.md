# Production staged-classification implementation

## Result

The best benchmarked method is now wired into LITEFile's lead-document worker:

1. `document_evidence_extraction/v1` extracts direct facts, official-form
   identity, selected options, classification excerpts, and structured monetary
   amounts from the limited PDF.
2. MarkItDown converts the first three pages once. Each later decision receives
   both pass-one evidence and this source text so the summary cannot erase a
   material qualifier.
3. `efile_taxonomy_classification/v2` selects court, category, case type, and
   filing type in order from the live hierarchy. The model returns a run-local
   `C###` reference; application code restores the exact current name and
   environment-specific route key.
4. An exact form-ID/name crosswalk lookup supplies advisory hints. Unverified
   mappings are never treated as deterministic gold. Express dollar amounts
   annotate amount-band candidates without filtering alternatives.

The extraction job now stores structured evidence, classification decisions,
and prompt/model/input provenance separately. Its flattened user-facing copy
includes every supported field, while exact live selections prefill the review
dropdowns. A single unambiguous claim-like amount prefills the existing amount
in controversy question; multiple or non-claim amounts do not.

## Live sentinel results

| Environment | PDF | Result |
| --- | --- | --- |
| Direct application service | MA-06 flattened small claim | Selected `District Court - Cambridge` → `Small Claims` → `Small Claim $501 - $2000` → `Statement of Small Claims entered through e-file process`; extracted claim amount `$1,275.00` and ignored conflicting crosswalk hints |
| Docker Compose web + worker + LocalStack | IL-02 flattened divorce petition | Browser upload passed and preselected `Lake County` → `Dissolution (Divorce) with Children` → `Dissolution (with children)` → `Petition Dissolution of Marriage/Civil Union` |

Both sentinels used the configured live model gateway and
`https://efile-test.suffolklitlab.org`. The final evidence call used inline PDF
input through the Responses API. Providers without that capability fall back to
Files API input and then real MarkItDown text; `evidence_input_mode` records
which path actually ran.

The Docker browser sentinel covered the actual upload endpoint, S3-compatible
storage, durable extraction queue, separate worker process, PDF analysis, live
taxonomy requests, database persistence, polling, and review-screen behavior.
The old worker test that replaced `analyze_document` remains for page-limit
isolation, but a new regression test downloads and converts the real synthetic
MA-01 PDF before substituting remote model responses.

## Findings during implementation

- The EFSP test service's `fileable_only=true` court query omitted Cambridge
  District Court and many other courts that expose valid fileable categories.
  The app now retrieves all named courts, hides explicit test/do-not-use
  entries, and validates the chosen path through downstream category/type
  calls. This also fixed the review UI, which otherwise could not display a
  correctly classified Cambridge route.
- The gateway's Chat Completions endpoint could not resolve IDs created through
  its Files API. Its Responses endpoint accepted the same PDF as inline file
  data and identified the printed document correctly, so native inline PDF is
  now preferred.
- MA-06 demonstrated why amount extraction and application-side arithmetic are
  both needed. The model selected the correct `$501 - $2000` case type from the
  explicit `$1,275.00` claim while retaining a separate `$50.00` court-cost fact.
- Route keys are stored only as current-run routing observations paired with
  the durable Tyler name and endpoint. The model never produces or copies them.
- Excluding the benchmark workspace from Docker reduced the measured build
  context from about 2.18 GB to 2.36 MB. The reviewed crosswalk is now bundled
  under `efile/data/`, so production does not depend on benchmark files.

## Verification

- Python: 486 tests passed, including native-file, staged-worker, live-reference
  integrity, amount-prefill, and real-PDF conversion coverage.
- JavaScript: 24 unit tests passed.
- Django: migration drift check and system checks passed.
- Ruff: repository check passed.
- Browser: the new Playwright real-upload sentinel passed first against host
  processes and again against the Docker Compose web/worker environment.
- Docker: final image build, migrations through `efile.0015`, web health check,
  extraction-worker startup, persisted `native_inline_pdf` analysis audit, and
  browser assertions passed.

## Limitations and next checks

- These are two synthetic initiating filings, not an estimate of production
  accuracy. Run the full cascade benchmark with predicted parents before
  changing confidence thresholds.
- The final Docker browser run used a flattened text PDF. Add a paired raster-only
  upload to verify that `native_inline_pdf` materially improves small header and
  footer evidence.
- The first-pass models still sometimes interpret a synthetic facsimile footer
  as a form or docket identifier. The review screen exposes those facts, but a
  focused footer sentinel should guide another evidence-prompt revision.
- No accessible `litefile-staging` Fly app existed in the authenticated Fly
  organization, so this study confirms the production-shaped local test
  deployment, not a public staging URL.
