---
id: deployment
title: Production deployment & cloud setup
sidebar_label: Deployment guide
sidebar_position: 4
---

# Production deployment & cloud setup <span className="wip-badge">WIP</span>

This guide explains how to deploy LITEFile to cloud infrastructure using **Docker**, **Fly.io**, and **AWS S3**.

---

## 1. Docker build & image optimization

LITEFile includes a production-ready `Dockerfile` using multi-stage caching and [Astral uv](https://astral.sh/uv).

### Preventing documentation from deploying with the Docker build

Documentation files (`docs/`, `node_modules/`, `.docusaurus/`) are strictly excluded from the Docker build context via `.dockerignore`. This ensures:
- Docker image size remains minimal (~200 MB).
- Fast build times and reliable layer caching.
- Documentation site is deployed independently (e.g. via GitHub Pages or static CDN) and is not packaged or deployed to Fly.io.

```dockerfile
# Dockerfile snippet
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app/efile_app
COPY efile_app/pyproject.toml efile_app/uv.lock* ./
RUN uv sync --frozen --no-install-project

COPY . /app
RUN uv sync --frozen

# Static asset collection
RUN DJANGO_SETTINGS_MODULE=efile.settings_staging \
    DJANGO_SECRET_KEY=build-static-collect-key \
    DATABASE_URL=sqlite:////tmp/build-collectstatic.sqlite3 \
    uv run python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["uv", "run", "gunicorn", "efile.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

---

## 2. Deploying to Fly.io

LITEFile uses `fly.toml` for staging and production hosting on [Fly.io](https://fly.io):

```toml
# fly.toml
app = 'litefile-staging'
primary_region = 'lax'

[env]
  DJANGO_SETTINGS_MODULE = "efile.settings_staging"

[deploy]
  # Run database migrations before each release
  release_command = "uv run python manage.py migrate --noinput --fake-initial"

[processes]
  app = "uv run gunicorn efile.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers 2 --timeout 60"
  extraction_worker = "uv run python manage.py process_document_extractions"
  code_index_worker = "uv run python manage.py refresh_filing_code_index --interval 86400"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = 'stop'
  auto_start_machines = true
  min_machines_running = 1
  processes = ['app']

[[vm]]
  memory = '1gb'
  cpu_kind = 'shared'
  cpus = 1
```

### Document extraction worker

Document analysis runs outside the web request in the `extraction_worker` process group. The web process stores the upload and queues a durable database job; the worker downloads the original lead document from S3 and records the extracted details on the filing draft. PDFs retain their stored form values for extraction. DOCX files are read locally with `docx2python`, and their text is supplied to analysis. Older binary DOC files use the converted PDF. Keep at least one worker Machine running so queued documents are analyzed.

By default, LITEFile sends only the first 20 PDF pages for analysis. Set `DOCUMENT_EXTRACTION_MAX_PAGES` to a positive integer to change that cap. DOCX text is limited to the first 100,000 characters with `DOCUMENT_EXTRACTION_MAX_TEXT_CHARS`; Word files have no reliable page boundaries. Review identifies when either limit omitted part of a document. `DOCUMENT_EXTRACTION_MAX_ATTEMPTS` controls how many times a failed job is tried before the filer is sent to manual review.

### Filing code search index

The `code_index_worker` builds search indexes for Illinois, Massachusetts, and
Vermont at startup, then refreshes them daily. Keep one Machine running in this
process group. It uses the same database and `EFSP_URL` as the web process.
Database migrations create a PostgreSQL GIN full-text index or a SQLite FTS5
inverted index automatically; pgvector and model downloads are not required.
Both use the same stemmed words, thesaurus, and whole-word matching. SQLite
looks up matching path IDs, jurisdiction, and new/existing-case status in FTS5
before ranking and grouping results, rather than scanning every filing path.
SQLite triggers keep the postings synchronized with catalog inserts, updates,
deletes, and transaction rollbacks. An existing SQLite installation's first FTS5
migration indexes its saved catalog locally; it does not fetch court data again.

To refresh once, run these commands from `efile_app/` in the target environment:

```bash
uv run python manage.py migrate --noinput
uv run python manage.py refresh_filing_code_index
# Or refresh just one state's complete catalog:
uv run python manage.py refresh_filing_code_index --jurisdiction vermont
```

Refreshes traverse all filing courts and their category, case-type, and filing-type
lists, including both new and existing filings. This can take time; it runs outside
web requests and the release command. Entries are staged in compressed disk storage
and inserted in batches. Each jurisdiction is replaced in one transaction only
after its complete catalog was fetched. A failed request or empty catalog preserves
the previous snapshot; the command reports failures and exits unsuccessfully in
one-shot mode. Temporary HTTP failures are retried before abandoning a refresh.
The recurring worker retries failed states after one minute (`--retry-interval`)
and skips fresh indexes, including after a restart. Monitor worker logs for
refresh failures. Complete court checkpoints are reused for up to six hours after
a failed build. `--cache-dir` controls their location; Compose uses
`/data/filing-code-cache` in the shared volume so a container replacement retains
progress. Checkpoints are separated by jurisdiction, source service, and rules
revision. Incomplete courts are never reused or published.

Local Docker Compose also starts `code_index_worker` after the web container is
healthy, using the shared database volume. For an already-running local stack,
run `docker compose up code_index_worker` to start it and watch progress.

Before the first successful refresh, the modal explains that search is unavailable
and the usual court lists remain available. The dialog does not trigger indexing,
but retries an unavailable search automatically while it stays open.
Results older than two days carry an out-of-date notice. Every selected path is checked against the live court
lists before it updates the form. A changed `EFSP_URL` or thesaurus revision requires
a fresh index, so test-server codes and incompatible search terms cannot leak into
another environment. Restart the web and index workers after changing search rules.

### Setting Fly.io production secrets:
```bash
fly secrets set \
  DJANGO_SECRET_KEY="generate-a-strong-random-key" \
  DATABASE_URL="postgres://..." \
  AWS_ACCESS_KEY_ID="AKIA..." \
  AWS_SECRET_ACCESS_KEY="..." \
  AWS_S3_BUCKET_NAME="litefile-production-documents" \
  AWS_S3_REGION_NAME="us-east-1" \
  OPENAI_API_KEY="sk-..." \
  GOTENBERG_URL="https://..." \
  GOTENBERG_USERNAME="..." \
  GOTENBERG_PASSWORD="..."
```

---

## 3. AWS S3 storage setup

LITEFile stores uploaded PDFs in a private S3 bucket and generates presigned URLs for e-file proxy document ingestion. Set `AWS_S3_REGION_NAME` to the bucket's actual region. Keep all four S3 Block Public Access settings enabled, use "Bucket owner enforced" object ownership, and do not add a public bucket policy or object ACLs. The proxy downloads each presigned URL with an HTTP GET; CORS is not needed for that server-to-server request.

### IAM policy

Attach this policy to the application IAM principal, replacing `YOUR-BUCKET-NAME`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDocumentsForConnectionCheck",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME",
      "Condition": {"StringLike": {"s3:prefix": "efile-documents/*"}}
    },
    {
      "Sid": "ManageDocuments",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:AbortMultipartUpload"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/efile-documents/*"
    }
  ]
}
```

For a bucket configured with an older `PublicReadGetObject` policy, remove that statement and verify all four public access blocks. If the bucket uses a customer-managed KMS key, grant the application principal the required `kms:GenerateDataKey` and `kms:Decrypt` permissions for that key as well. After deploying, upload a test PDF, verify that its unsigned object URL returns 403 and its fresh presigned URL downloads successfully, then delete the test object. Keep presigned URLs out of logs and issue reports because they grant temporary access.
