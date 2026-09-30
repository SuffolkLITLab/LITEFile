---
id: configuration
title: Configuration & environment variables
sidebar_label: Configuration reference
sidebar_position: 3
---

# Configuration & environment variables <span className="wip-badge">WIP</span>

LITEFile follows [Twelve-Factor App](https://12factor.net/) principles, configuring all environment-specific settings, API keys, database credentials, and storage parameters through environment variables.

---

## Environment variables reference

| Variable name | Required? | Default value | Description |
| :--- | :---: | :--- | :--- |
| `DJANGO_SETTINGS_MODULE` | Yes | `efile.settings_dev` | Django settings module (`efile.settings_dev`, `efile.settings_staging`, `efile.settings_prod`). |
| `DJANGO_SECRET_KEY` | Yes (Prod) | Insecure dev key | Cryptographic secret key used for session signing and CSRF tokens. |
| `DATABASE_URL` | Yes (Prod) | `sqlite:///db.sqlite3` | Database connection string (e.g., `postgres://user:pass@host:5432/dbname`). |
| `DJANGO_ALLOWED_HOSTS` | Yes (Prod) | `localhost,127.0.0.1` | Comma-separated list of allowed hostnames/domains. |
| `EFSP_URL` | No | `https://efile-test.suffolklitlab.org` | Base URL for the EFSP REST API endpoint. |
| `SUFFOLK_EFILE_API_KEY` | No | `""` | API authentication key for the EFSP proxy service. |
| `OPENAI_API_KEY` | Optional | `None` | API key for OpenAI or compatible LLM provider used for document extraction. |
| `OPENAI_BASE_URL` | Optional | `https://api.openai.com/v1/` | Base URL for OpenAI-compatible endpoint (or local LLM gateway). |
| `LITEFILE_PROMPTS_DIR` | Optional | Bundled `efile/prompts/` directory | Override path for the versioned LLM prompt catalog. |
| `DOCUMENT_EVIDENCE_MODEL` | Optional | First available small model | Exact deployed model used for direct document evidence extraction. |
| `DOCUMENT_CLASSIFICATION_MODEL` | Optional | First available medium model | Exact deployed model used for live taxonomy selection. |
| `DOCUMENT_EXTRACTION_MAX_PAGES` | No | `20` | Maximum original PDF pages supplied to the evidence pass; stored form values are preserved. |
| `DOCUMENT_EXTRACTION_MAX_TEXT_CHARS` | No | `100000` | Maximum locally extracted DOCX text characters supplied to analysis. Word files have no reliable page boundaries. |
| `DOCUMENT_CLASSIFICATION_SOURCE_PAGES` | No | `3` | Maximum pages converted with MarkItDown and retained as source evidence during taxonomy selection. |
| `FORM_CODE_CROSSWALK_PATH` | Optional | Bundled `efile/data/form_code_crosswalk.json` | Override path for exact official-form retrieval hints. |
| `AWS_ACCESS_KEY_ID` | Yes (Storage) | `""` | AWS IAM access key for document upload to S3. |
| `AWS_SECRET_ACCESS_KEY` | Yes (Storage) | `""` | AWS IAM secret access key. |
| `AWS_S3_BUCKET_NAME` | Yes (Storage) | `""` | S3 bucket name for court document storage. |
| `AWS_SESSION_TOKEN` | No | `""` | AWS session token when using temporary credentials. |
| `AWS_S3_REGION_NAME` | No | `us-east-1` | AWS region where the S3 bucket is hosted. |
| `DJANGO_LOG_LEVEL` | No | `DEBUG` (Dev) / `INFO` (Prod) | Logging verbosity for the `efile` application logger. |
| `GOTENBERG_URL` | Optional | `""` | Base URL for the Gotenberg document conversion API (e.g. `https://gotenberg-dev.fly.dev`). |
| `GOTENBERG_USERNAME` | Optional | `""` | HTTP basic auth username for the Gotenberg service. |
| `GOTENBERG_PASSWORD` | Optional | `""` | HTTP basic auth password for the Gotenberg service. |
| `DOCUMENT_PREPARATION_TIMEOUT_SECONDS` | No | `45` | Timeout for a conversion or flattening request. |

---

## Example `.env` file (development)

Create an `efile_app/.env` file for local development:

```bash
# efile_app/.env
DJANGO_SETTINGS_MODULE="efile.settings_dev"
DJANGO_SECRET_KEY="local-dev-secret-key-replace-in-production"

# AWS S3 Storage (Required for file uploads)
AWS_ACCESS_KEY_ID="your-aws-access-key-id"
AWS_SECRET_ACCESS_KEY="your-aws-secret-access-key"
AWS_S3_BUCKET_NAME="litefile-dev-bucket"
AWS_S3_REGION_NAME="us-east-1"

# AI Extraction (Optional)
OPENAI_API_KEY="sk-..."
```


## Document preparation and previews

Configure Gotenberg 8.16 or newer for Word conversion and PDF form flattening.
The service must support `/forms/libreoffice/convert` and `/forms/pdfengines/flatten`.
Use HTTPS and service credentials when connecting to a remote instance. Install
fonts used by your forms in Gotenberg: missing fonts can change pagination or layout.

LITEFile keeps an unchanged PDF byte for byte. When form fields need locking, it
preserves existing appearance streams and repairs missing or stale text appearances
with `pypdf` before Gotenberg flattens the fields. It rejects unreadable, encrypted,
XFA, digitally certificate-signed PDFs that would need flattening, and results with
missing pages, remaining fields, or lost filled-in text. Filers can upload a printed
PDF copy instead. These checks do not guarantee visual fidelity; every new filing
copy has a preview step before submission. Filers are asked to check every page;
Continue records that step without requiring a checkbox.

Word conversion requests tagged PDF output and lossless images. It does not
rasterize the document or certify accessibility conformance. Flattening can change
accessibility tags, links, or annotations. The private original is retained separately
from the filing PDF and is available for download. Only the filing copy reaches the
court. Analysis reads the original PDF and its stored form values, or text extracted
locally from the original DOCX with `docx2python`. Older binary DOC files use the
converted PDF for analysis. The AI opt-out applies to every format.
Existing editable drafts without preparation metadata are prepared when
the filer opens the preview step. Missing stored uploads must be replaced; legacy
clients cannot bypass preparation or the preview step. Removing a document or expiring an unclaimed handoff cleans up both private
copies when another draft does not reference them.

State YAML can override the default policy:

```yaml
document_preparation:
  flatten_pdf_forms: false
text:
  upload_documents:
    preparation_help_unflattened: >-
      LITEFile converts Word documents to PDF. PDF form fields are kept as uploaded.
      Check the filing PDFs before continuing.
```

The default is to lock interactive fields. Vermont explicitly enables this policy
and links to the court's preparation instructions. PDFs without form widgets are
left unchanged, including already flattened and remediated documents.

PDF.js is pinned in `efile_app/package-lock.json` and served from the application,
including its worker, fonts, and character maps. Run `npm ci` in `efile_app` before
local previews; its install script copies these assets. The Docker build generates
the same assets in a separate Node stage. Document bytes come from an authenticated,
draft-scoped endpoint with `Cache-Control: private, no-store`, so previewing does
not require public storage URLs or S3 CORS configuration.
