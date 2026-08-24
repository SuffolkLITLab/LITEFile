# Benchmarking & evaluation suite

This directory contains benchmarking suites, test corpora, and evaluation tools for LITEFile's document extraction and e-filing pipeline.

---

## Directory overview

- [synthetic/](synthetic/README.md): The primary synthetic benchmark dataset consisting of 30 target court forms across Massachusetts, Vermont, and Illinois, paired as interactive and flattened PDFs (60 documents total), plus 6 standalone official-template motion filings and diagnostic evaluation scripts.
- [promptfoo/](promptfoo/README.md): A Promptfoo prompt × model matrix over all 66 PDFs, with deterministic set scoring and confidence-aware Tyler label reviews.

---

## Datasets

### Synthetic dataset (`synthetic/`)

The **synthetic dataset** is a standardized test corpus designed to evaluate LITEFile's automated document extraction and classification capabilities.

Key characteristics:
- **Multi-state coverage**: 10 target filings each for **Massachusetts**, **Vermont**, and **Illinois** (30 unique form types).
- **Paired PDF variants**: Each form scenario is provided in both an **interactive AcroForm PDF** (with fillable form fields) and a **flattened PDF** (with appearances baked into page graphics).
- **Standalone motion filings**: 6 official-template motion PDFs (2 per jurisdiction) to test extraction and abstention behavior on open-ended motion forms.
- **Official form layouts**: The 30 paired filings use court-published blank templates downloaded from Massachusetts, Vermont, and Illinois court websites.
- **Fictional data**: All names, addresses, docket numbers, dates, and case facts are fictional. No real personal identifying information (PII) or confidential legal data is included. PDF metadata identifies the filled forms as LITEFile benchmark fixtures.

For full documentation on data schema, source forms, field extractability mappings, and execution instructions, see [synthetic/README.md](synthetic/README.md).

---

## Quick start

To run extraction across the synthetic dataset using LITEFile's extraction service:

```bash
cd /home/quinten/LITEFile
PYTHONPATH=efile_app DJANGO_SETTINGS_MODULE=efile.settings python benchmarking/synthetic/run_litefile_extraction.py > extraction_results.jsonl
```

To evaluate the extraction output against diagnostic expectations:

```bash
python benchmarking/synthetic/evaluate_litefile_results.py extraction_results.jsonl
```
