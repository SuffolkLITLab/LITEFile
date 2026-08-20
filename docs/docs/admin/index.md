---
id: index
title: Administrator & deployment guide overview
sidebar_label: Overview (WIP)
sidebar_position: 1
---

# Administrator & deployment guide <span className="wip-badge">Work in progress</span>

:::warning Work in progress (WIP)
This section contains technical documentation for system administrators, DevOps engineers, and developers hosting or contributing to the LITEFile application.
:::

LITEFile is built as a lightweight, production-grade Django ASGI web application designed for high security, low operational overhead, and straightforward deployment on modern container platforms like **Fly.io**, AWS ECS, or Kubernetes.

---

## Technical stack at a glance

- **Backend runtime**: Python 3.12 with [Astral uv](https://astral.sh/uv) package manager
- **Web framework**: Django 5.2 (ASGI) with Gunicorn and Uvicorn workers
- **Database**: SQLite (local development) / PostgreSQL with connection pooling (staging & production)
- **Static assets**: WhiteNoise with compression and cache manifests
- **Document storage**: AWS S3 with pre-signed URLs and IAM least-privilege policies
- **E-filing integration**: Tyler Technologies EFM / EFSP REST API
- **AI / OCR engine**: OpenAI-compatible LLM gateway with MarkItDown PDF processing

---

## Guides in this section

- [**System architecture**](./architecture.md): Core components, data flow, and request lifecycle.
- [**Configuration & environment variables**](./configuration.md): Complete reference of all required and optional environment variables.
- [**Deployment guide**](./deployment.md): Step-by-step instructions for deploying to Fly.io, configuring AWS S3, and managing database migrations.
- [**Local development & testing**](./development.md): Setting up your local development environment, running Pytest, executing Playwright end-to-end filing tests, and linting.
