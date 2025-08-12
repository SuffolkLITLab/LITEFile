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

## Project Layout

- `mysite/manage.py` — Django management script
- `mysite/efile/settings.py` — Project settings (uses SQLite by default; DB file at `mysite/db.sqlite3`)
- `mysite/efile/urls.py` — URL routing
- `mysite/efile/templates/` — HTML templates
- `mysite/efile/static/` — Static assets

## Notes

- Default settings run with `DEBUG=True` and SQLite for local development.
