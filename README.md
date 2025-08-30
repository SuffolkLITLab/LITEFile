# Form Submission MVP

A minimal Django app for form submission and review. The Django project lives under `efile_app/` with settings in `efile_app/efile/`.

## Quick Start

- __Requirements__
  - Python 3.10+
  - uv

  
### Using uv (recommended)

- __0) Install uv__ (one-time)
  - macOS (Homebrew):
    ```bash
    brew install uv
    ```
  - Or official installer:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

- __1) Sync dependencies__
  From the project root (this will create `.venv/` and install deps from `pyproject.toml`):
  ```bash
  uv sync
  ```

- __2) Initialize the database__
  ```bash
  cd mysite
  uv run python manage.py migrate
  ```

- __3) Run the development server__
  ```bash
  uv run python manage.py runserver
  ```
  Then open http://127.0.0.1:8000/login in your browser.

#### Activate the venv instead of using `uv run` (optional)

`uv sync` creates `.venv/`. You can activate it and run Django commands normally:

- macOS/Linux:
  ```bash
  source .venv/bin/activate
  cd efile_app
  python manage.py migrate
  python manage.py runserver
  ```

- Windows (PowerShell):
  ```powershell
  .venv\Scripts\Activate.ps1
  cd mysite
  python manage.py migrate
  python manage.py runserver
  ```

Deactivate with `deactivate` when you're done.

## Optional

- __Create an admin user__
  - With uv:
    ```bash
    uv run python manage.py createsuperuser
    ```
  Admin will be available at `/admin/` after you start the server.

- __Static files__
  During development, static files are served automatically. No `collectstatic` is needed.

## Development: dev dependencies and Ruff

Ruff is configured in `pyproject.toml` under `[tool.ruff]`.

- __Using uv__
  - Install dev tools: 
    ```bash
    uv sync --group dev
    ```
  - Lint the codebase:
    ```bash
    uv run ruff check .
    ```
  - Auto-format (optional):
    ```bash
    uv run ruff format .
    ```

Notes: Ruff targets Python 3.10, line length 120, and excludes Django migrations (`**/migrations/*`).

## Testing

Pytest is configured via `pyproject.toml` to use `pytest-django`.

- __Install dev deps__ (once):
  ```bash
  uv sync --group dev
  ```

- __Run all tests__ (from project root):
  ```bash
  pytest -q
  ```

- __Select tests__:
  ```bash
  pytest mysite/efile/ -q                 # only the efile app
  pytest -k "login and not slow" -q       # expression match
  pytest mysite/efile/tests/test_smoke.py::test_login_page_renders -q
  ```

- __Speed tips__:
  ```bash
  pytest --reuse-db -q            # keep the test DB between runs
  pytest -n auto -q               # run in parallel (pytest-xdist)
  ```

- __Coverage__ (optional):
  ```bash
  pytest --cov=mysite --cov-report=term-missing
  ```

Notes:
- `DJANGO_SETTINGS_MODULE` is set to `efile.settings` in `[tool.pytest.ini_options]`.
- Tests are discovered under `mysite/`. An example smoke test lives at `mysite/efile/tests/test_smoke.py`.

## End-to-End Testing (Playwright)

Playwright tests are located in `efile_app/tests/` and provide browser-based testing of the complete user workflow. These are intended to be run manually and are not part of the CI/CD pipeline because they produce
side-effects (e.g. filing new cases in EFSP) and rely on external APIs (e.g. EFSP again). The tests stop short
of the document upload step as that would touch S3. We also wanted to avoid filing new cases into Tyler as part
of the current end-to-end testing.

### Setup

- __Install Playwright__ (one-time):
  ```bash
  npm install -g playwright
  playwright install
  ```

- __Environment variables__: Create a `.env` file in the project root with:
  ```bash
  E2E_TEST_USERNAME=your_test_email@example.com
  E2E_TEST_PASSWORD=your_test_password
  E2E_TEST_BASE_URL=http://localhost:8000  # optional, defaults to localhost:8000
  ```

### Running Tests

- __Start the Django server__ first:
  ```bash
  cd efile_app
  uv run python manage.py runserver
  ```

- __Run all Playwright tests__:
  ```bash
  cd efile_app
  npx playwright test
  ```

- __Run specific tests__:
  ```bash
  npx playwright test expert-form-name-change
  npx playwright test expert-form-order-of-protection
  npx playwright test expert-form-forfeiture-of-seized-property
  ```

- __Run with UI mode__ (interactive):
  ```bash
  npx playwright test --ui
  ```

### Available Tests

- **`expert-form-name-change`**: Tests the complete workflow for filing a name change case
- **`expert-form-order-of-protection`**: Tests the complete workflow for filing an order of protection case
- **`expert-form-forfeiture-of-seized-property`**: Tests the complete workflow for filing a forfeiture of seized property case

All tests:
1. Log in with provided credentials
2. Navigate to the expert form
3. Fill out court selection and case details
4. Complete required party information
5. Verify the document upload page loads correctly
6. Take screenshots for visual verification

Screenshots are saved to `screenshots/` directory.

## Type checking (Ty)

Ty (a Rust-based type checker) is configured in `pyproject.toml` under `[tool.ty.src]`.

- __Run a one-off check__:
  ```bash
  uv run ty check
  ```

- __Watch mode__ (re-run on changes):
  ```bash
  uv run ty watch
  ```

## Pre-commit hooks

Pre-commit hooks are configured in `.pre-commit-config.yaml` to run Ruff formatting/linting and type checking on commits, plus tests on push.

- __Install pre-commit hooks__ (one-time setup):
  ```bash
  uv run pre-commit install
  uv run pre-commit install --hook-type pre-push
  ```

- __Run hooks manually__:
  ```bash
  uv run pre-commit run --all-files    # run all hooks on all files
  uv run pre-commit run pytest         # run just the pytest hook
  ```

**Note**: The pytest hook runs on `pre-push` stage to keep commits fast. If you skip the pre-push hook installation, tests won't run automatically before pushing.

## Project Layout

- `mysite/manage.py` — Django management script
- `mysite/efile/settings.py` — Project settings (uses SQLite by default; DB file at `mysite/db.sqlite3`)
- `mysite/efile/urls.py` — URL routing
- `mysite/efile/templates/` — HTML templates
- `mysite/efile/static/` — Static assets

## Notes

- Default settings run with `DEBUG=True` and SQLite for local development.
