# Agent guidelines & repository notes

This document provides conventions and context for AI coding assistants working in the `LITEFile` repository.

---

## 1. Documentation & style conventions

- **Sentence case for titles & headings**: All documentation titles, sidebar labels, navigation items, page headings (`#`, `##`, `###`), and captions must use **sentence case** (e.g., *How e-filing works*, *Step-by-step filing walkthrough*, *Jurisdiction & court YAML configuration*, *System architecture & tech stack*).
  - Capitalize only the first word of the heading and proper nouns (e.g., *LITEFile*, *PDF*, *Docassemble*, *AssemblyLine*, *Fly.io*, *AWS S3*, *Django*, *PostgreSQL*, *Ruff*, *Pytest*, *Illinois*, *Massachusetts*, *Vermont*, *Tyler*).
  - Do not use Title Case for headings or navigation labels.
- **Tone & accessibility**: Maintain plain, accessible language for user-facing guides, avoiding unnecessary technical jargon.
- **Multi-state architecture**: Documentation and user-facing resources must support multi-state expansion (e.g., Illinois, Massachusetts, Vermont, and nationwide legal aid/court directories). Avoid hardcoding references to a single state unless describing a state-specific configuration file.

---

## 2. Documentation site structure (`docs/`)

- **Docusaurus v3**: The documentation site is located in `docs/` targeting `@docusaurus/core` v3.
- **GitHub Pages deployment**: Documentation builds and deploys via GitHub Actions (`.github/workflows/deploy-docs.yml`) to `https://litefile-docs.suffolklitlab.org`.
- **CNAME**: Custom domain is defined in `docs/static/CNAME` (`litefile-docs.suffolklitlab.org`).
- **Internal notes**: Internal developer notes, MVP vision briefs, and evaluation notes live in `docs/developer-notes/` and must not be published to the public Docusaurus docs tree (`docs/docs/`).
- **Docker isolation**: `docs/`, `node_modules/`, and `.docusaurus/` are excluded in `.dockerignore` so they are never copied into backend container images.

---

## 3. Backend & development commands

- **Python & Django**: Python application root is in `efile_app/`.
- **Package manager**: Use Astral `uv` for dependency management:
  ```bash
  cd efile_app
  uv sync --group dev
  uv run pytest -q
  uv run ruff check .
  uv run ty check
  ```
- **Docusaurus local commands**:
  ```bash
  cd docs
  npm start       # Start dev server at http://localhost:3000
  npm run build   # Build production static bundle to docs/build/
  npm run serve   # Preview production build
  ```
