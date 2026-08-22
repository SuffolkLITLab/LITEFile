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

PDF analysis runs outside the web request in the `extraction_worker` process group. The web process stores the upload and queues a durable database job; the worker downloads the lead PDF from S3 and records the extracted details on the filing draft. Keep at least one worker Machine running so queued documents are analyzed.

By default, LITEFile sends only the first 20 PDF pages for analysis. Set `DOCUMENT_EXTRACTION_MAX_PAGES` to a positive integer to change that cap. `DOCUMENT_EXTRACTION_MAX_ATTEMPTS` controls how many times a failed job is tried before the filer is sent to manual review.

### Setting Fly.io production secrets:
```bash
fly secrets set \
  DJANGO_SECRET_KEY="generate-a-strong-random-key" \
  DATABASE_URL="postgres://..." \
  AWS_ACCESS_KEY_ID="AKIA..." \
  AWS_SECRET_ACCESS_KEY="..." \
  AWS_S3_BUCKET_NAME="litefile-production-documents" \
  AWS_S3_REGION_NAME="us-east-1" \
  OPENAI_API_KEY="sk-..."
```

---

## 3. AWS S3 storage setup

LITEFile stores uploaded PDFs in Amazon S3 and generates pre-signed URLs for Tyler EFSP document ingestion.

### S3 bucket policy:
Apply this policy to allow document retrieval:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    }
  ]
}
```

### IAM user policy:
Create an IAM user with least-privilege access for the application:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:PutObjectAcl", "s3:GetObject"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME"
    }
  ]
}
```
