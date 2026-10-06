# LITEFile

A minimal Django app for form submission and review. The Django project lives under `efile_app/` with settings in `efile_app/efile/`.

## Quick start

- __Requirements__
  - Python 3.10+
  - uv

### Single-command local startup (`run_all.sh`)

To quickly run the entire local development stack without building the full Docker container:

```bash
./run_all.sh
```

This script:

- Verifies Astral `uv` and synchronizes the local virtual environment (`efile_app/.venv`)
- Automatically initializes `efile_app/.env` from `.env.example` if needed
- Starts LocalStack (S3 mock) in Docker if Docker is running
- Applies Django database migrations
- Runs the Django development server (`http://127.0.0.1:8000`) and background extraction worker together
- Starts the filing code index worker, which checks for changed courts daily and imports only their bulk code exports
- Cleanly stops all child processes upon pressing `Ctrl+C`

Filing code search becomes available after the first successful import. Deploy the proxy's `filing_catalog` API first; during rollout, `--legacy-code-crawl` explicitly enables the older full crawler.

Run `./run_all.sh --help` to see additional options (e.g., custom ports, running without Docker, or `--no-code-index` to skip the court code index worker).

### Using uv manually

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
  cd efile_app
  uv run python manage.py migrate --run-syncdb
  ```

- __3) Run the development server__
  ```bash
  uv run python manage.py runserver
  ```
  Then open http://127.0.0.1:8000/login in your browser.

- __4) Run the document extraction worker__
  In a second terminal, from `efile_app/`:
  ```bash
  uv run python manage.py process_document_extractions
  ```
  The upload page stores PDFs immediately; this worker analyzes queued lead documents in the background.

#### Activate the venv instead of using `uv run` (optional)

`uv sync` creates `.venv/`. You can activate it and run Django commands normally:

- macOS/Linux:
  ```bash
  source .venv/bin/activate
  cd efile_app
  python manage.py migrate --run-syncdb
  python manage.py runserver
  ```

- Windows (PowerShell):
  ```powershell
  .venv\Scripts\Activate.ps1
  cd efile_app
  python manage.py migrate --run-syncdb
  python manage.py runserver
  ```

Deactivate with `deactivate` when you're done.

## Optional

- __Create an admin user__
  - Set `LITEFILE_STAFF_BOOTSTRAP_USERNAME` and a unique
    `LITEFILE_STAFF_BOOTSTRAP_PASSWORD` through your shell or secret manager, then:
    ```bash
    cd efile_app
    uv run python manage.py bootstrap_staff
    ```
  Store the generated TOTP setup URI in your password manager. Alternatively,
  supply its Base32 secret using `LITEFILE_STAFF_BOOTSTRAP_TOTP_SECRET`.
  With the default private path, open http://127.0.0.1:8000/staff-7c83f0a2/.
  Every staff role requires a local password and TOTP, including superusers.
  See the [staff setup and local demo runbook](docs/developer-notes/staff-privacy-and-analytics.md)
  for local sample data, deployment switches, and recovery.

- __Static files__
  During development, static files are served automatically. No `collectstatic` is needed.

## AWS S3 setup (required for file uploads)

The application uses AWS S3 for document storage and file uploads. Follow these steps to set up your S3 bucket:

### 1. Create an S3 bucket

- Log into the AWS Console and navigate to S3
- Create a new bucket (e.g., `litefile-your-suffix`)
- Choose a region and set `AWS_S3_REGION_NAME` to that same region.
- Keep all four "Block public access" settings enabled. Use "Bucket owner enforced" object ownership and do not grant object ACLs.
- Tags can be created to help track ownership of resources and is useful for cost tracking, environment tracking, etc.
- Use the default S3 managed encryption unless you also grant the app access to a customer-managed KMS key.

### 2. Create IAM user and permissions

Create an IAM principal for the application with this policy, replacing `YOUR-BUCKET-NAME`. The app uploads, downloads, and deletes documents under `efile-documents/`; its S3 connection check lists only that prefix. A public bucket policy is not needed for presigned URLs.

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

### 3. Configure environment variables

Copy the example environment file and update the S3 settings:

```bash
cp efile_app/.env.example efile_app/.env
```

Edit `efile_app/.env` with your AWS credentials:

Remove the `AWS_S3_ENDPOINT_URL` line from the copied example when using AWS; that endpoint is for LocalStack.

```bash
# AWS S3 configuration
AWS_ACCESS_KEY_ID = "your-aws-access-key-id-here"
AWS_SECRET_ACCESS_KEY = "your-aws-secret-access-key-here"
# Set AWS_SESSION_TOKEN too when using temporary credentials.
AWS_S3_BUCKET_NAME = "your-bucket-name-here"
AWS_S3_REGION_NAME = "your-bucket-region"
```

LITEFile generates time-limited presigned URLs that the e-file proxy can retrieve with an ordinary HTTP GET. The signing principal needs `s3:GetObject`, but the bucket does not need public access or CORS for this server-to-server download. For an existing bucket, remove any `PublicReadGetObject` statement and confirm all four public access blocks are enabled. Check that an unsigned object URL returns 403 while a fresh presigned URL downloads the file. Do not paste presigned URLs into issue reports or logs; they grant access until they expire.

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
    uv run djlint .
    ```
  - Auto-format:
    ```bash
    uv run ruff format .
    ```
  - Auto-format HTML, JS, and CSS
    ```bash
    uv run djlint --reformat .
    uv run css-beautify -r efile/static/css/*.css
    uv run js-beautify -r efile/static/js/*.js
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
  pytest efile_app/efile/ -q                 # only the efile app
  pytest -k "login and not slow" -q       # expression match
  pytest efile_app/efile/tests/test_smoke.py::test_login_page_renders -q
  ```

- __Speed tips__:
  ```bash
  pytest --reuse-db -q            # keep the test DB between runs
  pytest -n auto -q               # run in parallel (pytest-xdist)
  ```

- __Coverage__ (optional):
  ```bash
  pytest --cov=efile_app --cov-report=term-missing
  ```

Notes:
- `DJANGO_SETTINGS_MODULE` is set to `efile.settings` in `[tool.pytest.ini_options]`.
- Tests are discovered under `efile_app/`. An example smoke test lives at `efile_app/efile/tests/test_smoke.py`.

## End-to-end testing (Playwright)

Playwright tests are located in `efile_app/tests/` and provide browser-based testing of the complete user workflow. These are intended to be run manually and are not part of the CI/CD pipeline because they produce
side-effects (e.g. filing new cases in EFSP) and rely on external APIs (e.g. EFSP again). The tests stop short
of the document upload step as that would touch S3. We also wanted to avoid filing new cases into Tyler as part
of the current end-to-end testing.

### Setup

- __Install Playwright dependencies__ (one-time):
  ```bash
  cd efile_app
  npm install
  npx playwright install
  ```

- __Environment variables__: Create a `.env` file in the `efile_app/` directory with:
  ```bash
  # Tyler test-EFM login. The Python test suite reads the same two names.
  TESTS_TYLER_USERNAME=your_test_email@example.com
  TESTS_TYLER_PASSWORD=your_test_password
  E2E_TEST_BASE_URL=http://localhost:8000  # optional, defaults to localhost:8000
  ```

### Configuration

The Playwright configuration includes several important settings:

- **Global Setup**: Automatically loads environment variables and validates credentials before running tests
- **Timeout**: Extended to 10 minutes (600,000ms) to accommodate form filling and external API calls
- **Base URL**: Configured for `http://localhost:8000` (Django development server)
- **Retry Strategy**: 2 retries on CI, 0 retries locally
- **Parallel Execution**: Disabled on CI (1 worker) to avoid conflicts with external services
- **Browser**: Currently configured for Chromium only (Firefox and Safari commented out)

### Running tests

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

- __Run one spec__:
  ```bash
  cd efile_app
  npx playwright test tests/reorganized-filing-matrix.spec.js
  ```

- __Run with UI mode__ (interactive):
  ```bash
  cd efile_app
  npx playwright test --ui
  ```

- __Run in headed mode__ (see browser):
  ```bash
  cd efile_app
  npx playwright test --headed
  ```

**Note**: The global setup automatically validates your `.env` configuration before running tests. If environment variables are missing, tests will fail with a clear error message.

### Test architecture

The Playwright tests use a modular architecture with shared utilities:

- **`tests/setup.js`**: Global setup that loads environment variables and validates credentials before any tests run
- **`tests/test-utils.js`**: Shared utilities including `loginViaLogout()`, `loginViaLoginPage()`, and `getTestConfig()` functions
- **`playwright.config.js`**: Playwright configuration with global setup enabled, extended timeout, and CI-specific settings

#### Login utilities

The `test-utils.js` module provides two login methods:

- **`loginViaLogout(page, config)`**: Logs in via the `/logout` endpoint (ensures clean session) - this is the default
- **`loginViaLoginPage(page, config)`**: Logs in via the `/login` page
- **`loginUser(page, config)`**: Alias for `loginViaLogout()` for backward compatibility

### Available tests

- **`reorganized-filing-matrix.spec.js`**: Files one envelope per scenario through
  the whole workflow -- start a filing, upload a document, confirm the case codes,
  answer the people and fees screens, submit -- for both new cases and filings into
  an existing case, across a matrix of Illinois courts and case types.

It really files, in the Tyler test EFSP, so it is skipped unless you ask for it:

```bash
cd efile_app
RUN_FILING_MATRIX=1 npx playwright test tests/reorganized-filing-matrix.spec.js
```

Screenshots are saved to `screenshots/` directory and excluded from git via `.gitignore`.

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

Pre-commit hooks are configured in `.pre-commit-config.yaml` to run Ruff, JavaScript ESLint/SonarJS, Prettier, Bandit, and type checking on commits, plus tests on push.

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

## Project layout

- `efile_app/manage.py` — Django management script
- `efile_app/efile/settings.py` — Project settings (uses SQLite by default; DB file at `efile_app/db.sqlite3`)
- `efile_app/efile/urls.py` — URL routing
- `efile_app/efile/templates/` — HTML templates
- `efile_app/efile/static/` — Static assets

## Notes

- Default settings run with `DEBUG=True` and SQLite for local development.
