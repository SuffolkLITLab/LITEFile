# Resumable crosswalk field review tool

## Purpose

This review tool lets a human verify the assigned form title and printed form
ID, then verify or correct the category, case type, and filing type for every
candidate mapping. It keeps review answers in a separate database so the
source crosswalk remains unchanged while review is in progress.

Each mapping has a read-only live lookup panel. The panel uses the form's
jurisdiction and filing phase, resolves the selected court, and then loads the
staged category → case type → filing type hierarchy. Changing a category or
case type refreshes its dependent choices. Saved lookup context includes the
endpoint, names, transient route keys, and timestamp for audit purposes.

## Run locally

From the repository root:

```bash
cd efile_app
DJANGO_SETTINGS_MODULE=efile.settings_dev .venv/bin/python manage.py migrate
DJANGO_SETTINGS_MODULE=efile.settings_dev .venv/bin/python manage.py load_crosswalk
DJANGO_SETTINGS_MODULE=efile.settings_dev .venv/bin/python manage.py runserver 127.0.0.1:8001
```

Open <http://127.0.0.1:8001/review/> and enter a reviewer name. The default
lookup endpoint is `https://efile-test.suffolklitlab.org`. Override it before
starting the server when needed:

```bash
export CROSSWALK_REVIEW_EFSP_URL=https://efile-test.suffolklitlab.org
```

The supplied runner binds to `0.0.0.0:8001` so a browser outside the
workspace can reach it. Override `CROSSWALK_REVIEW_BIND` when the server should
remain local to the workspace process.

The local SQLite review database is `efile_app/db.sqlite3`, which is ignored
by Git. To use a separate location, set `DATABASE_URL` or run the standalone
deployment with `CROSSWALK_REVIEW_DATABASE_PATH=/data/crosswalk-review.sqlite3`.

## Review and resume

1. Open a form from “Continue reviewing”.
2. Compare the title and printed ID with the local PDF preview or source link.
3. Use “Save progress” whenever you want to stop. Partial answers are saved.
4. For mappings, choose a court and load live options. The lookup is
   jurisdiction-aware and cascades through the live hierarchy.
5. Mark each field Correct, Incorrect, or Unsure. If a value is corrected,
   leave the corrected value selected and mark the assigned value Incorrect.
6. Use “Save & next unreviewed” to advance. It requires all identity and
   taxonomy field verdicts for the current form.

The progress page shows both the legacy mapping-verdict count and the new
field-level completion count for the selected reviewer. “Next unreviewed” in
the new workflow requires the title, form ID, and all three taxonomy fields on
each mapping to have a saved verdict.

## Saved data and exports

- `FormReview` stores the reviewed title, reviewed printed ID, two identity
  verdicts, notes, reviewer, and timestamps.
- `MappingVerdict` stores the reviewed category, case type, filing type,
  field-level verdicts, lookup context, notes, reviewer, and timestamps.
- `export.csv` contains one row per saved mapping answer, with the form-level
  answer repeated for convenience.
- `export.json` contains every form, including identity-only forms with no
  mappings, and all saved reviewer answers.

The live lookup endpoint only reads the staged taxonomy. It never writes
taxonomy data or changes the crosswalk JSON.

## Verified court lookup behavior

The lookup was tested through the running review app on August 28, 2026. Four
issues found during end-to-end testing were corrected:

- Preloaded court options now put the transient Tyler route key in
  `data-code`, which is where the browser lookup reads it.
- Valid current court keys containing a colon or space, such as
  `sc:chittendon` and `reaknox 2`, pass server validation while path traversal
  and URL delimiters remain blocked.
- “Load live options” now loads courts when necessary and continues through
  categories, case types, and filing types in the same click.
- When an assigned value is absent from the current staged list, it remains
  visible as a stale assigned value while the first valid live option is
  selected so the dependent lookup can continue.
- Crosswalk-only phases such as `paper_only` and `not_applicable` remain
  visible as assigned evidence but are no longer sent to Tyler. Each mapping
  has a separate lookup phase selector limited to Tyler's supported `initial`
  and `subsequent` values. It defaults to the assigned phase when compatible
  and otherwise starts with `initial`; the selected lookup phase is saved in
  the lookup context.

The staged taxonomy client retries transient connection and read timeouts up
to three times. Errors are still shown in the mapping card if staging remains
unavailable.

A browser JavaScript simulation using the script rendered by the running
review page verified the complete one-click sequence with stale assigned
values: courts → categories → case types → filing types. Live calls through
the review app then completed these representative initial-filing paths:

| Jurisdiction | Court | Courts | Categories | Case types | Filing types | Elapsed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Massachusetts | `352` | 146 | 14 | 1 | 23 | 0.65 s |
| Illinois | `dupage` | 207 | 21 | 15 | 24 | 0.69 s |
| Vermont | `sc:chittendon` | 22 | 3 | 77 | 110 | 0.73 s |

The focused backend and review-app suite passed 57 tests. The rendered
Massachusetts form page included `data-code="352"`, and the local PDF endpoint
returned a valid PDF with `X-Frame-Options: SAMEORIGIN`.

The phase fallback was also tested in a real headless browser against
`MA-CJD-200`, whose assigned phase is `paper_only`. One click loaded 146 courts,
3 categories, 26 case types, and 2 filing types from staging in 1.49 seconds
with no browser errors. Changing the lookup phase to `subsequent` reran the
cascade successfully and wrote `subsequent` to the saved lookup context.

## Local PDF previews

The review page uses the downloaded forms in `court_forms/` instead of trying
to embed a remote court URL. The local form registry is read from
`court_forms/form_registry.json` (with `form_registry.csv` as a fallback), and
the PDF is served through the review app's `pdf/<canonical-id>/` route. The
browser therefore receives a normal local `application/pdf` response, with an
“Open in new tab” link as a fallback for browsers that do not render inline PDF
viewers.

Because the application applies a default clickjacking header of
`X-Frame-Options: DENY`, the local PDF route explicitly uses `SAMEORIGIN` so
the review page can display its own local PDF in the side-by-side viewer. The
route still serves only a registry-resolved file under the configured forms
root.

### Rendered XFA previews

Some court PDFs are dynamic XFA forms: ordinary PDF text extraction returns an
Adobe placeholder even though a rendered visual copy exists. The registry now
uses a converted image PDF for the review preview only after OCR confirms that
the rendered first page contains real form content. The original downloaded PDF
continues to supply printed-ID verification, so switching the preview cannot
weaken deterministic identity evidence.

The current merge verified 156 rendered PDFs. Its per-file OCR evidence is in
[`artifacts/rendered-xfa-merge.json`](artifacts/rendered-xfa-merge.json).
Re-run the merge with:

```bash
cd efile_app
uv run python ../benchmarking/promptfoo/scripts/merge_rendered_xfa_forms.py --apply
```

The resolver indexes source URL, source filename, normalized form ID, and
normalized title. It ignores punctuation, spacing, and accents when comparing
text, prefers exact source URL matches, and only uses ID or title matches when
they identify one file. This avoids silently displaying the wrong form when a
state reuses an ID or has translated duplicates. The index is cached in memory
after its first load, so subsequent checks are constant-time.

### Printed form ID validation

Local file resolution alone is not identity evidence: a title-only match can
point at a different court's similarly named form. Before a PDF is embedded in
the review tool, the assigned crosswalk form ID must now appear in the PDF's
extractable text. The comparison ignores punctuation, spacing, and line breaks
inside the ID, but keeps alphanumeric boundaries so a short ID cannot match
inside a larger word or code. The PDF route applies the same guard, so an
unverified file cannot be opened directly through the review application.

The August 28, 2026 full pass is saved in
[`local-form-id-audit.json`](local-form-id-audit.json). Of the active
crosswalk records, 219 have a deterministic PDF-to-form-family association:
108 by printed ID alone, 18 by an exact registry-title tie-breaker, and 93 as
multiple official PDF variants of the same printed-ID form family. Six exact-ID
sets remain unresolved because their titles do not corroborate the same form
family. Forms with no printed-ID evidence have no local PDF association unless
they are explicitly title-identified records with no claimed form ID. Those
records may use one unambiguous local title match and otherwise show the
official source link when one is available.

For example, `MA-CJD-200` assigned `CJD 200` had been matched by title to
`MA_Summons_and_Order_of_Notice_7e640467.pdf`. That PDF is a Housing Court
summons and contains no `CJD 200`; the title-only association has been removed
from the generated local-PDF crosswalk. A headless-browser check confirmed the
absence of a local association and confirmed that a
verified form (`IL-AOIC-004`, `ANS`) still loads its local PDF normally.

Run the reusable audit with:

```bash
cd efile_app
uv run python manage.py audit_local_form_ids --forms-root ../court_forms \
  --output ../benchmarking/promptfoo/lab-notebook/reviews/2026-08-27-crosswalk-field-review-tool/local-form-id-audit.json
uv run python manage.py build_local_form_id_index --forms-root ../court_forms
```

This is an extractable-text check, not OCR. A missing result means the current
local PDF cannot support deterministic ID verification; it does not by itself
prove that a form ID was never printed on a scanned image.

### Evidence-only form registry

On August 28, 2026, the active canonical registry was reduced from 891 records
to the 219 forms with a positive printed-ID form-family association. It then
added 1,009 title-identified records from downloaded PDFs that have an exact,
usable title but no asserted form ID. These entries intentionally have no
filing mapping: title evidence identifies a document, not its Tyler route.

Four title records represent 27 language-specific Vermont PDFs: each uses one
English canonical title and its Arabic, French, Nepali, Somali, Spanish,
Swahili, and/or Vietnamese names as aliases. Verified printed-ID families
likewise include their downloaded translated and revised titles as aliases.

This leaves 1,228 active crosswalk identities. Metadata labels such as
`(Untitled)`, `View Form`, and a bare language name remain outside the
title-matching crosswalk because they cannot identify one form.

For live upload matching, an unverified registry code is never copied into a
crosswalk `form_id`. When the PDF has a usable exact title, it is instead added
as a no-ID title identity, with the registry code retained only as provenance.
The production matcher can then return an exact form-name match without
treating a potentially incorrect code as evidence. For example, the live
matcher now recognizes Vermont's `Affidavit of No Assets` by title while
returning no asserted form ID.

For records with low-signal crawl metadata, the title recovery pass reads the
visible PDF text (pypdf first, then `pdftotext`) and promotes only a specific
first-page heading. It recovered and imported 13 additional title identities
in the current corpus. Generic headings and XFA/LiveCycle placeholder text are
left unresolved rather than being treated as titles.

### Unrecognized downloaded titles

The reproducible analysis in
[`artifacts/unrecognized-local-forms.json`](artifacts/unrecognized-local-forms.json)
separates the 1,945 downloaded PDFs into exact-ID coverage and follow-up
queues. Usable title-only records are now imported; the remaining no-ID PDFs
have only low-signal metadata such as `(Untitled)`. PDFs with a registry-supplied
ID that could not be verified in PDF text remain in a separate queue for better
extraction/OCR or a manual title-based identity decision. The report keeps
title-only identities separate from records that merely share a title alias
with a code-bearing form, so a failed ID check cannot be bypassed through an
alias.

Run the title synchronization and queue analysis with:

```bash
cd benchmarking/promptfoo
uv run python scripts/sync_title_identity_crosswalk.py
uv run python scripts/analyze_unrecognized_local_forms.py
cd ../../efile_app
uv run python ../benchmarking/promptfoo/scripts/extract_low_signal_pdf_titles.py --apply
```

`MA-CJD-200` (`CJD 200`) was removed in this pass. It had been introduced in
the original hand-authored staged registry with only a generic Mass.gov landing
page, no official PDF URL, and a `not_current` source-verification status. No
downloaded form contained its code. The cleanup also removes stale database
rows on crosswalk reload, but refuses to delete any record with saved reviewer
answers.

Reapply or verify the cleanup with:

```bash
cd benchmarking/promptfoo
uv run python scripts/prune_unverified_form_ids.py \
  --index ../../court_forms/form_id_matches.json
uv run python scripts/prune_unverified_form_ids.py \
  --index ../../court_forms/form_id_matches.json --check
```

The default root is the repository's `court_forms/` directory. To use a
different mounted dataset, set this before starting the app:

```bash
export CROSSWALK_REVIEW_FORMS_ROOT=/path/to/court_forms
```

The index is built once at startup and uses hash maps for lookup. Forms without
a safe local match show a clear message and a link to the official source when
one is available; they do not attempt a remote iframe preview.

## Tests

Run the review-app tests with:

```bash
cd efile_app
uv run pytest -q crosswalk_review/tests.py efile/tests/test_taxonomy_classification.py
uv run ruff check crosswalk_review
uv run djlint crosswalk_review/templates/crosswalk_review --check
```
