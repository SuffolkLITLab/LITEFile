---
id: development
title: Local development, testing & quality assurance
sidebar_label: Local dev & testing
sidebar_position: 5
---

# Local development & quality assurance <span className="wip-badge">WIP</span>

This guide covers running LITEFile locally, running test suites (Pytest and Playwright), type checking, and code formatting.

---

## 1. Local setup with Astral `uv`

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Sync dependencies**:
   ```bash
   uv sync --group dev
   ```

3. **Initialize the SQLite database**:
   ```bash
   cd efile_app
   uv run python manage.py migrate --run-syncdb
   ```

4. **Start the development server**:
   ```bash
   uv run python manage.py runserver
   ```
   Open `http://127.0.0.1:8000` in your browser.

5. **Start the document extraction worker in a second terminal**:
   ```bash
   cd efile_app
   uv run python manage.py process_document_extractions
   ```
   Uploads complete in the web process. This worker analyzes queued lead PDFs in the background.

---

## 2. Running automated tests

### Pytest (unit & integration tests)
```bash
# Run all unit tests
pytest -q

# Run efile app tests only
pytest efile_app/efile/ -q

# Run with test coverage report
pytest --cov=efile_app --cov-report=term-missing
```

### Playwright (end-to-end filing matrix tests)
Playwright tests in `efile_app/tests/` verify the complete 14-step user workflow against the Tyler test EFSP.

```bash
cd efile_app
npm install
npx playwright install

# Run the complete reorganized filing matrix spec in Tyler test environment
RUN_FILING_MATRIX=1 npx playwright test tests/reorganized-filing-matrix.spec.js
```

---

## 3. Code formatting & type checking

LITEFile enforces high code quality through Ruff and Ty:

```bash
# Run Ruff linting and auto-formatting
uv run ruff check .
uv run ruff format .

# Run Ty type checking
uv run ty check

# Run pre-commit hooks
uv run pre-commit run --all-files
```
