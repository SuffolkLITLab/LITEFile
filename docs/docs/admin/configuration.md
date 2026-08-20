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
| `AWS_ACCESS_KEY_ID` | Yes (Storage) | `""` | AWS IAM access key for document upload to S3. |
| `AWS_SECRET_ACCESS_KEY` | Yes (Storage) | `""` | AWS IAM secret access key. |
| `AWS_S3_BUCKET_NAME` | Yes (Storage) | `""` | S3 bucket name for court document storage. |
| `AWS_S3_REGION_NAME` | No | `us-east-1` | AWS region where the S3 bucket is hosted. |
| `DJANGO_LOG_LEVEL` | No | `DEBUG` (Dev) / `INFO` (Prod) | Logging verbosity for the `efile` application logger. |

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
