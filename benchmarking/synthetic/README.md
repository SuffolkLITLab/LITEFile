# Synthetic benchmark dataset

This directory contains the **synthetic benchmark dataset** for LITEFile, designed to test and evaluate automated document extraction, form classification, field normalization, and abstention behavior across multiple state court jurisdictions.

> [!IMPORTANT]
> **Synthetic test notice**: All documents, individuals, corporate entities, addresses, docket numbers, case captions, dates, and narrative facts in this dataset are entirely synthetic and fictional. Every PDF is watermarked and visibly marked `SYNTHETIC TEST DOCUMENT - NOT FOR FILING` or `TEST COPY - NOT FOR FILING`. These files are facsimiles created solely for extraction and benchmarking purposes.

---

## Dataset overview

The synthetic benchmark dataset covers **30 distinct court filing targets** across three jurisdictions (**Massachusetts**, **Vermont**, and **Illinois**; 10 forms per state), rendered in both **interactive** and **flattened** PDF formats (60 paired documents total), plus **6 synthetic motion facsimiles**.

- **Interactive PDFs** (`filled_pdfs/interactive/`): Forms populated with synthetic scenario data in fillable AcroForm widget fields.
- **Flattened PDFs** (`filled_pdfs/flattened/`): The same 30 synthetic filings rendered with field appearances burned permanently into page content and AcroForm fields removed, simulating scanned or print-to-PDF court filings.
- **Synthetic motion facsimiles** (`motions/`): Standalone synthetic motion filings patterned after jurisdictional caption and motion conventions to evaluate how extractors handle open-ended motion formats and whether they properly abstain from hallucinating underlying case types.

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
- **IL-10**: Motion (ATJ-style estate motion)

---

## File and directory structure

| Path | Description |
|---|---|
| `manifest.jsonl` / `paired_manifest.jsonl` | Primary JSONL dataset manifest linking each target ID to jurisdiction, form metadata, official source URL, interactive & flattened PDF paths, scenario facts, and extractability targets. |
| `seed_manifest.jsonl` | Baseline seed manifest containing initial target records, scenarios, and expected extraction fields. |
| `motion_cases.jsonl` | Subset of 6 motion cases with explicit abstention targets and allowed inference rules. |
| `extractability.jsonl` | Diagnostic field extractability definitions separating visible fields, semantic fields, optional inferences, and do-not-require fields. |
| `extractability.csv` | Tabular CSV summary of field extractability across all 30 target forms. |
| `extractability.md` | Human-readable markdown guide for field extractability expectations by state. |
| `sources.md` | Reference list of official source URLs for all 30 court form templates. |
| `litefile_schema_snapshot.json` | Reference snapshot of LITEFile extraction field definitions and normalization rules. |
| `pdf_structure_check.json` | Pre-computed structure validation metrics (page count, AcroForm field count, text character count) for both PDF variants. |
| `run_litefile_extraction.py` | Benchmark execution script that runs LITEFile's `analyze_document()` across all synthetic documents. |
| `evaluate_litefile_results.py` | Diagnostic scoring script that evaluates extraction output against `extractability.jsonl`. |
| `filled_pdfs/interactive/` | 30 interactive fillable PDFs (IL-01..10, MA-01..10, VT-01..10). |
| `filled_pdfs/flattened/` | 30 flattened non-fillable PDFs (IL-01..10, MA-01..10, VT-01..10). |
| `motions/` | 6 standalone synthetic motion facsimiles (2 each for IL, MA, VT). |

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

From the repository root:

1. **Run extraction across the synthetic dataset**:
   ```bash
   PYTHONPATH=efile_app DJANGO_SETTINGS_MODULE=efile.settings python benchmarking/synthetic/run_litefile_extraction.py > extraction_results.jsonl
   ```

2. **Evaluate extraction results**:
   ```bash
   python benchmarking/synthetic/evaluate_litefile_results.py extraction_results.jsonl
   ```
