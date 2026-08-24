# Synthetic benchmark dataset

This directory contains the **synthetic benchmark dataset** for LITEFile, designed to test and evaluate automated document extraction, form classification, field normalization, and abstention behavior across multiple state court jurisdictions.

> [!IMPORTANT]
> **Fictional data notice**: All people, organizations, addresses, docket numbers, dates, and narrative facts in the filled documents are fictional benchmark data. The 30 paired filings use court-published PDF templates, and their PDF metadata identifies them as LITEFile benchmark fixtures. Do not file them with a court.

---

## Dataset overview

The synthetic benchmark dataset covers **30 distinct court filing targets** across three jurisdictions (**Massachusetts**, **Vermont**, and **Illinois**; 10 forms per state), rendered in both **interactive** and **flattened** PDF formats (60 paired documents total), plus **6 standalone official-template motion copies** used by the motion-specific evaluations.

- **Official blank templates** (`official_templates/`): Court-published forms downloaded from the URLs in `official_sources.json`.
- **Interactive PDFs** (`filled_pdfs/interactive/`): Official forms populated with fictional scenario data in their native AcroForm fields. The Massachusetts summary process summons is an image-only official exemplar, so its entries use a PDF overlay.
- **Flattened PDFs** (`filled_pdfs/flattened/`): The same 30 filings printed to PDF with field appearances burned into page content and AcroForm fields removed.
- **Standalone motion filings** (`motions/`): Copies of the six relevant official-template filings from the paired corpus, kept at stable motion-specific paths for evaluations of open-ended formats and abstention behavior.

---

## Jurisdiction and form coverage

### Massachusetts (MA-01 through MA-10)

- **MA-01**: Complaint for Divorce under G.L. c. 208, § 1B (CJD 101B)
- **MA-02**: Joint Petition for Divorce under G.L. c. 208, § 1A (CJD 101A)
- **MA-03**: Complaint for Support, Custody, Parenting Time (CJD 109)
- **MA-04**: Complaint for Separate Support (CJD 102)
- **MA-05**: Petition to Change Name of Adult (CJP 27)
- **MA-06**: Statement of Small Claim and Notice for eFiling (Small Claims eFile)
- **MA-07**: Summary Process Summons and Complaint (Summary Process)
- **MA-08**: Motion to the Court and Affidavit (TC0049)
- **MA-09**: Motion (CJD 400)
- **MA-10**: Request for Default Judgment (Mass. R. Civ. P. 55(b)(3))

### Vermont (VT-01 through VT-10)

- **VT-01**: Complaint for Divorce/Legal Separation/Dissolution without Children (400-00836NoChildren)
- **VT-02**: Complaint for Divorce/Legal Separation/Dissolution with Children (400-00836Children)
- **VT-03**: Small Claims Complaint (100-00257)
- **VT-04**: Civil Division Answer (100-00051)
- **VT-05**: Complaint for Relief from Abuse (400-00150C)
- **VT-06**: Petition of Adult to Change Name (700-00122)
- **VT-07**: Petition to Appoint Custodial Guardian for a Minor (700-00070C)
- **VT-08**: Miscellaneous Motion - Family Division (400-00830)
- **VT-09**: Civil Division Motion (100-00053)
- **VT-10**: Motion to Modify Child Support and/or Maintenance Supplement (400-00803)

### Illinois (IL-01 through IL-10)

- **IL-01**: Complaint or Petition (ATJ Complaint/Petition)
- **IL-02**: Petition for Divorce with Children (Divorce suite)
- **IL-03**: Eviction Complaint (Eviction suite)
- **IL-04**: Small Claims Complaint (CS-C 702.1)
- **IL-05**: Request for Name Change (Name Change Adult)
- **IL-06**: Petition for Guardianship of a Minor (Minor Guardianship)
- **IL-07**: Petition for Order of Protection (Order of Protection)
- **IL-08**: Application for Waiver of Court Fees (Fee Waiver Civil)
- **IL-09**: Motion (ATJ 801.7)
- **IL-10**: Motion (ATJ 801.7), populated for an estate-administration scenario

---

## File and directory structure

| Path | Description |
|---|---|
| `manifest.jsonl` / `paired_manifest.jsonl` | Primary JSONL dataset manifest linking each target ID to jurisdiction, form metadata, official source URLs, blank template, interactive and flattened PDF paths, scenario facts, and extractability targets. |
| `seed_manifest.jsonl` | Baseline seed manifest containing initial target records, scenarios, and expected extraction fields. |
| `motion_cases.jsonl` | Subset of 6 motion cases with explicit abstention targets and allowed inference rules. |
| `extractability.jsonl` | Diagnostic field extractability definitions separating visible fields, semantic fields, optional inferences, and do-not-require fields. |
| `extractability.csv` | Tabular CSV summary of field extractability across all 30 target forms. |
| `extractability.md` | Human-readable markdown guide for field extractability expectations by state. |
| `sources.md` | Reference list of official source URLs for all 30 court form templates. |
| `official_sources.json` | Machine-readable direct download or court media URLs used to retrieve the blank forms. |
| `download_official_forms.py` | Reproducible downloader for the 30 official templates. |
| `build_official_corpus.py` | Fills the fictional scenarios, creates interactive and flattened pairs, cleans visible fixture artifacts in manifests, and refreshes the structure report. |
| `official_templates/` | Court-published blank PDF forms. |
| `litefile_schema_snapshot.json` | Reference snapshot of LITEFile extraction field definitions and normalization rules. |
| `pdf_structure_check.json` | Pre-computed structure validation metrics (page count, AcroForm field count, text character count) for both PDF variants. |
| `run_litefile_extraction.py` | Benchmark execution script that runs LITEFile's `analyze_document()` across all synthetic documents. |
| `evaluate_litefile_results.py` | Diagnostic scoring script that evaluates extraction output against `extractability.jsonl`. |
| `filled_pdfs/interactive/` | 30 interactive fillable PDFs (IL-01..10, MA-01..10, VT-01..10). |
| `filled_pdfs/flattened/` | 30 flattened non-fillable PDFs (IL-01..10, MA-01..10, VT-01..10). |
| `motions/` | 6 standalone official-template motion filings (2 each for IL, MA, VT). |

---

## Expected extraction and abstention policy

The extraction schema targets standard normalized keys:
- `document title`
- `court`
- `filing type`
- `case category`
- `case type`
- `docket number`
- `case title`
- Party name fields (`plaintiff or petitioner names`, `defendant or respondent names`, `other party names`)
- `document date`

### Abstention policy for motions and unstated fields

Fields are intentionally marked as *abstention targets* (`do_not_require`) when a document does not provide sufficient evidence. For example, generic motion forms typically identify the filing type (e.g., *Motion to Continue*) but do not state the underlying case type (e.g., *Contract/Debt Collection* vs. *General Civil*). An extraction model is rewarded for abstaining rather than hallucinating unsupported classifications.

---

## Running extraction and evaluation

To refresh the official forms and rebuild the paired corpus:

```bash
python benchmarking/synthetic/download_official_forms.py --force
python benchmarking/synthetic/build_official_corpus.py --sync-metadata
```

From the repository root:

1. **Run extraction across the synthetic dataset**:
   ```bash
   PYTHONPATH=efile_app DJANGO_SETTINGS_MODULE=efile.settings python benchmarking/synthetic/run_litefile_extraction.py > extraction_results.jsonl
   ```

2. **Evaluate extraction results**:
   ```bash
   python benchmarking/synthetic/evaluate_litefile_results.py extraction_results.jsonl
   ```
