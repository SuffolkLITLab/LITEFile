# Document preparation and preview validation

Validated September 30, 2026 for [LITEFile issue #113](https://github.com/SuffolkLITLab/LITEFile/issues/113).
Branch: `feature/document-preparation-preview`.
Validation gist: https://gist.github.com/nonprofittechy/54857d2ed0b841a486dbf7a30b1ad915.

## Result and engine choice

Use Gotenberg for Word conversion and PDF flattening, with the existing `pypdf`
dependency repairing missing or stale text appearance streams first. PDFtk is
used only in the comparison harness; it is not a runtime dependency.

The local scan found 12 PDFs with populated form values, comprising 11 distinct
files after SHA-256 deduplication and 22 pages. These come from ALWeaver,
ALDashboard, AppearanceEfile, MLHDivorceAndCustody, USCISApplications and
CLAGuardianship repositories. The corpus includes template defaults, whitespace
values and checked controls; supplemental synthetic values exercise multiline
text, signatures, Unicode and complete packets. It should continue to grow as
more representative completed filings become available.

| Method | Accepted local specimens | Fields remaining in accepted outputs |
| --- | --- | --- |
| Raw Gotenberg flatten route | 11 / 11 | 0 |
| LITEFile preparation pipeline | 11 / 11 | 0 |
| PDFtk Java 3.3.3 `flatten` | 10 / 11 | 0 |

PDFtk rejected ALWeaver's option-group fixture. Full provenance, SHA-256 hashes,
page counts, text counts and results are in
[corpus-comparison.json](https://github.com/SuffolkLITLab/LITEFile/blob/feature/document-preparation-preview/docs/developer-notes/issue-113/corpus-comparison.json).
Source documents and filled values stay local; the published report contains
metadata and synthetic screenshots.

Text extraction initially made raw Gotenberg look sufficient. Raster inspection
revealed that its appearance generation placed three multiline answers on one
line when `/AP` was missing. This matches QPDF's documented limits on appearance
generation. LITEFile creates the text appearance with `pypdf`, clears
`NeedAppearances`, then lets Gotenberg flatten that appearance. Existing usable
appearances remain intact. The synthetic reproducer shows the difference:

![Raw Gotenberg joins the three lines](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/12-raw-gotenberg-multiline.png)

![LITEFile preserves three separate lines](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/13-repaired-multiline.png)

An EOIR missing-appearance stress case containing accented names demonstrated
another engine limitation. The prepared result retained form fields, so LITEFile
rejected it with a printed-PDF recovery instruction. The automated checks also
reject lost filled text, changed page counts and unreadable responses. Preview
and filer confirmation remain necessary for layout, fonts, clipping, checkbox
and signature fidelity. This work does not establish universal PDF compatibility.

## Court forms and packet checks

The current [Vermont File & Serve FAQ](https://www.vtcourts.gov/about-vermont-judiciary/electronic-access/electronic-filing/faqs)
requires form-fillable PDFs to be saved as flat files before filing. Vermont's
YAML explicitly enables flattening and supplies plain-language upload guidance
with that source. Other jurisdictions can set `flatten_pdf_forms: false` and
provide their own guidance through `ui_text`.

Downloaded the official [Small Claims Answer, form 100-00126, July 2025](https://www.vtcourts.gov/sites/default/files/documents/100-00126%20%E2%80%93%20Small%20Claims%20Answer_0.pdf)
and filled it with synthetic names, a synthetic docket, a selected checkbox,
a three-line answer and a typed `/s/` signature. Checked the rasterized filing
copy on both pages. The checkbox, names, answer lines and signature remained
visible. Appended two synthetic exhibit pages and verified the prepared packet
has four pages, no form fields, preserved signature text and an intact last
exhibit page. No court filing or fee request was made for these documents.

![Vermont answer retains the checkbox and multiline response](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/09-vt-small-claims-answer.png)

![Vermont answer retains its typed signature](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/10-vt-signature.png)

## Browser validation

Ran Chromium against Django's live test server with real Gotenberg conversion,
real PDF.js rendering and an in-memory S3 test double. Documents and account
identity were synthetic. This validates app behavior without uploading test
files to production storage or contacting a court. The separate PDF corpus
comparison calls the configured Gotenberg service and writes local artifacts.

Checked the following:

- Selecting and uploading a two-page PDF with missing multiline appearances and a two-page DOCX together.
- Loading actual filing bytes through the authenticated preview endpoint.
- Rendering both PDFs, moving to page two, zooming and retaining selectable text layers.
- Keeping the originals separately and providing original and filing-copy download links.
- Requiring a confirmation checkbox for every document before continuing.
- Rendering expandable PDFs in the organize and fees screens, with assertions that each expected page loaded.
- A 390-pixel mobile viewport with no horizontal page overflow.
- Invalid-PDF upload guidance with the existing files retained.
- A simulated 503 from document storage, followed by successful retry after reopening the preview.
- Zero browser page errors and zero Axe violations in the preview screen.

The initial browser run caught a compatibility problem in PDF.js 6's modern
bundle on the installed Chromium. The shipped assets now use PDF.js's official
legacy build, including its compatibility polyfills. A second run caught
repeated page-region landmark labels across documents; those labels now identify
both the document and the page. The final run passes. A final evidence review also caught a redirected organize
page; the fixture now supplies synthetic case data and asserts the page URL and
heading before capturing that screenshot. Court choices and payment accounts
are stubbed, and the backend fee estimate is stubbed.

![Preview step with the actual multiline PDF](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/02-multiline-preview.png)

![Word filing copy rendered in the preview](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/04-word-preview.png)

![Expandable preview while organizing documents](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/05-organize-preview.png)

![Expandable preview while choosing payment](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/14-fees-preview.png)

![Mobile preview](https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots/06-mobile-preview.png)

[All screenshots and the Axe result](https://github.com/SuffolkLITLab/LITEFile/tree/feature/document-preparation-preview/docs/developer-notes/issue-113/screenshots)
include the second-page view, selection screen, invalid upload, preview failure
and final packet exhibit.

## Automated validation

| Check | Result |
| --- | --- |
| `uv run pytest -q` | 1,231 passed; 1 opt-in browser test skipped |
| Opt-in real Gotenberg and Chromium test | 1 passed |
| Conversion and preview tests with Gotenberg environment variables cleared | Passed; final full suite also runs with these variables cleared |
| GitHub accessibility workflow | Passed |
| `npm run test:unit` | 64 passed |
| `uv run ruff check .` and formatting | Passed |
| `uv run ty check` | Passed |
| `npm run lint:js` and Prettier check | Passed |
| New Django template lint and format | Passed |
| Stylelint | 0 errors; 19 existing warnings in other stylesheets |
| Bandit | Passed after removing a production assertion |
| `uv run pip-audit --local --skip-editable` | No known vulnerabilities found |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `docker build -t litefile:issue-113 .` | Passed; generated and collected PDF.js assets |
| Docusaurus `npm run build` | Passed |

Regression coverage includes complete filing flows in Vermont, Illinois and
Massachusetts; later fee-waiver uploads; interview handoffs and replacement
PDFs; private preview ownership and draft isolation; original downloads;
unchanged PDFs; damaged and unsupported inputs; service timeout; oversized
output; conservative loss checks; batch rollback and orphan cleanup; server-side
approval; stale preview fingerprints; and original/review metadata preservation
when legacy clients rebuild supporting rows.

The existing npm dependency tree reports four audit findings in development/test
dependencies. No finding names the new PDF.js package. Those existing dependencies
were left at their locked versions to keep this feature's dependency changes
focused. Accessibility testing checks the preview controls and generated tagged
Word PDF structure; it does not certify every filing PDF as PDF/UA compliant.

The first GitHub dependency audit found four advisories in the pre-existing
`virtualenv` 20.36.1 development dependency. Updated the lockfile to virtualenv
21.7.13 and its required dependencies, then verified the audit passes and that
it creates a working virtual environment. The relevant fixes are documented in
[virtualenv's release history](https://virtualenv.pypa.io/en/latest/changelog.html#v21-7-13-2026-09-18).

CI also exposed mocked conversion tests that depended on a locally configured
Gotenberg URL. The test fixture now sets a synthetic service URL explicitly;
The conversion and preview tests pass with all Gotenberg environment variables
cleared. The opt-in integration test still uses the real configured service.

## Regression review

Addressed the follow-up review with tests that start from unprepared or stale
server state rather than relying on already reviewed fixtures:

| Concern | Behavior checked |
| --- | --- |
| Lead storage-key replacement | Clears preparation, original metadata and approval; deletes superseded copies after commit while keeping shared references |
| Legacy supporting uploads | Prepares stored DOCX/PDF bytes on preview, rejects acknowledgement before preparation, and blocks direct submission |
| Stale preview fingerprint | Includes preparation, original key, size and document update time in addition to row and filing key |
| Indirect annotation arrays | Resolves and validates the array before iterating; accepts the indirect-array regression specimen |
| Handoff preparation errors | Permanent input/conversion rejection returns 422; storage and conversion-service outages return 503 |
| Extraction timing | Registers the job creation with `transaction.on_commit`; a rolled-back transaction does not queue extraction |
| Waiver write failure | Database errors after storing original and filing copies remove both staged objects |
| Handoff replacement cleanup | Deletes old objects after commit, preserving objects referenced by another draft |
| Special text-field appearances | Skips literal-value matching for comb, password, formatted, rich-text and hidden/no-view fields; retains structural and ordinary visible-text checks |

The existing extraction queue is a database record, so creating it inside the
original atomic transaction was already isolated from worker reads and rollback.
The callback now makes the commit boundary explicit. Downstream-flow fixtures
explicitly represent prepared and acknowledged documents; the new bypass tests
keep their documents unprepared. The accessibility seed command also marks its
downstream fixture as prepared and confirmed, with a regression test for this
state. A concurrency unit test also now mocks court
choices instead of intermittently depending on a live court response.

## Reproduction

From `efile_app`, configure Gotenberg credentials and run:

```bash
uv sync --group dev
npm ci
uv run pytest -q
npm run test:unit
uv run python ../testing/validate_document_preparation.py \
  --output /tmp/litefile-pdf-validation --render
DOCUMENT_PREPARATION_BROWSER_TESTS=1 \
DOCUMENT_PREPARATION_EVIDENCE_DIR=/tmp/litefile-browser-evidence \
uv run pytest -q -s efile/tests/test_document_preparation_browser.py
```

The corpus script defaults to `~/docassemble-*`, accepts repeatable `--source`
paths, and writes source hashes and engine results without filled values. It
requires PDFtk for comparison and Poppler for `--render`; the application requires
neither. The browser test requires a Playwright Chromium install. For an existing
local browser, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its executable path.

Relevant engine documentation:
[Gotenberg flatten route](https://gotenberg.dev/docs/manipulate-pdfs/flatten-pdfs),
[Gotenberg Word conversion](https://gotenberg.dev/docs/convert-with-libreoffice/convert-to-pdf),
and [QPDF appearance generation](https://qpdf.readthedocs.io/en/stable/cli.html#option-generate-appearances).
