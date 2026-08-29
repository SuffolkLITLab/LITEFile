# Deterministic form-identifier scan

## Result

The lead-document workflow now performs a deterministic form-identifier scan
before it accepts the AI's printed form-ID transcription.

The registry is compiled once per process and registry path into a cached
Aho–Corasick automaton. The document text is compacted to lowercase ASCII
alphanumerics for matching, while source boundaries are retained so punctuation,
spaces, and line breaks can vary without allowing a match inside a larger word.

The sampled Illinois codes are now represented in the production crosswalk.
Six existing Illinois records have a `form_id_aliases` entry, and three sampled
statewide forms that were absent from the registry have code-backed records with
no guessed Tyler mappings:

| Sample | Printed code | Revision | Registry identity | Tyler mapping |
| --- | --- | --- | --- | --- |
| IL-01 | `ATJ 561.1` | 02/26 | `IL-ATJ-561.1` | Not added; identity only |
| IL-02 | `ATJ 105.3` | 03/25 | `IL-ATJ-105.3` | Not added; identity only |
| IL-03 | `E-C 3502.3` | 06/24 | `IL-AOIC-040` | Existing crosswalk mappings |
| IL-04 | `CS-C 702.1` | 08/20 | `IL-AOIC-209` | Existing crosswalk mappings |
| IL-05 | `ATJ 303.10` | 03/25 | `IL-AOIC-170` | Existing crosswalk mappings |
| IL-06 | `1601.1` | 11/25 | `IL-AOIC-1601.1` | Not added; identity only |
| IL-07 | `ATJ 403.5` | 05/25 | `IL-AOIC-184` | Existing crosswalk mappings |
| IL-08 | `ATJ 601.9` | 08/25 | `IL-AOIC-091` | Existing crosswalk mappings |
| IL-09 | `ATJ 801.7` | 08/25 | `IL-AOIC-152` | Existing crosswalk mappings |
| IL-10 | `ATJ 801.7` | 08/25 | `IL-AOIC-152` | Existing crosswalk mappings |

The code and revision values were initially read from page one of the local
official templates with `pypdf`; the direct official PDF URL and landing page
are recorded in
[`illinois_form_code_verification.json`](./illinois_form_code_verification.json).
The rendered pages, rather than extracted text, are the source for human
confirmation.

A unique match is authorized only when it is the earliest exact identifier on
page one. This prevents an identifier mentioned later in instructions from
overriding the document's own header. Identifiers shorter than four normalized
characters are not scan patterns because Illinois group labels such as `SC` and
`NC` generate ordinary-word false positives. Ambiguous and body-only matches are
recorded for diagnostics and fall back to the AI evidence path.

The runtime sequence is now:

1. Convert the first classification pages to MarkItDown text.
2. Extract selectable text from the analyzed PDF with `pypdf`.
3. Search that text through the cached reverse identifier index.
4. Run the evidence AI for the remaining fields.
5. If the scan found one safe identifier, replace the AI's form-ID value with
   the registry's exact printed value before taxonomy classification.

The scan metadata is persisted with the extraction, including the source,
elapsed milliseconds, all observed matches, and the deterministic match. The
Tyler taxonomy is still not selected solely from this result; the existing live
hierarchy and filer confirmation remain authoritative.

## Human visual review

Generate the review worksheet with:

```bash
efile_app/.venv/bin/python benchmarking/promptfoo/lab-notebook/studies/2026-08-27-deterministic-form-identifier-scan/render_illinois_form_code_review.py
```

Then open
[`illinois-form-code-review/index.html`](./illinois-form-code-review/index.html).
Each card places the rendered first page beside the assigned code, revision,
canonical identity, registry form ID, and source links. Compare the code printed
at the bottom of the actual page with the red assigned value. This review is
intentionally separate from the automated text scan.

The generated worksheet is a local derived artifact and is ignored by Git. The
ten samples are currently recorded as `verified` in the checked-in manifest and
in `illinois-form-code-review/review_status.json`, based on the user's visual
confirmation on 2026-08-27. For a future correction, edit the status file, set
the affected sample to `needs_correction`, add notes, and rerun the renderer.

## Local corpus validation

The validation command is:

```bash
efile_app/.venv/bin/python benchmarking/promptfoo/lab-notebook/studies/2026-08-27-deterministic-form-identifier-scan/validate_local_forms.py
```

For a focused Illinois check, run:

```bash
efile_app/.venv/bin/python benchmarking/promptfoo/lab-notebook/studies/2026-08-27-deterministic-form-identifier-scan/verify_illinois_form_codes.py
```

The Illinois verifier checks every sample in the manifest against the official,
interactive, and flattened local PDFs. It requires the expected printed code to
be present on page one and requires the deterministic scan to return the
expected canonical form. It exits nonzero on any mismatch; add `--json` for
machine-readable output or `--dataset official_templates` to run one variant.
This is an internal consistency check between the manifest, extracted text, and
registry; it does not replace the visual review above.

It checks the 30 local forms in all three available PDF variants:

| Dataset | Expected deterministic matches | Max PDF text + scan | Average PDF text + scan |
| --- | ---: | ---: | ---: |
| Official templates | 27/30 | 326 ms | 82 ms |
| Interactive filled PDFs | 27/30 | 363 ms | 74 ms |
| Flattened filled PDFs | 27/30 | 402 ms | 67 ms |

The same 27 forms matched in every variant, so the implementation produced
81/90 expected deterministic results. The scan itself averaged under 2 ms per
document after PDF text was available; the larger timings include `pypdf` text
extraction. All observed deterministic matches were the expected dataset form.

The remaining three forms are registry-coverage/version findings, not latency
failures:

- `MA-06` and `MA-07` do not have matching printed identifiers in the current
  registry.
- The local `VT-10` PDF prints `400-00803`, while the registry contains the
  distinct versioned identifier `400-00803-4`. The punctuation-tolerant scan
  intentionally does not erase meaningful suffixes.

The Illinois code additions make form identity deterministic, but they do not
turn an identity match into a Tyler filing-type selection. The three new
Illinois records deliberately have empty mappings until a separate source-backed
taxonomy association is reviewed.

## Safety observations

The local forms include references to other forms in their instructions. For
example, Vermont divorce forms mention financial-affidavit identifiers. The
scanner reports those occurrences but does not authorize them when the main
form identifier occurs earlier on page one. `VT-10` also demonstrated why this
guard matters: its body mentions `400-00813A`, but no page-one deterministic
match was authorized.

The direct implementation is in
[`taxonomy_classification.py`](../../../../../efile_app/efile/services/taxonomy_classification.py)
and the worker integration is in
[`document_extractions.py`](../../../../../efile_app/efile/services/document_extractions.py).
