# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system deps (curl for uv installer, build tools only if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy project metadata first for better layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies without installing the project code yet (faster rebuilds)
RUN uv sync --frozen --no-install-project

# Copy the rest of the source code
COPY . .

# Install the project itself (editable-like install)
RUN uv sync --frozen

EXPOSE 8000

# For Django dev server; override in compose for different commands
CMD ["uv", "run", "python", "efile_app/manage.py", "runserver", "0.0.0.0:8000"]
