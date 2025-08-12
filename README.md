# Form Submission MVP

A minimal Django app for form submission and review. The Django project lives under `mysite/` with settings in `mysite/efile/`.

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
  cd mysite
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
