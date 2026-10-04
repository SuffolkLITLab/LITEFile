# Testing help

## Local S3 (LocalStack)

`compose.yml` in the repo root starts [LocalStack](https://docs.localstack.cloud/)
alongside the web container and creates the bucket automatically
(`testing/localstack-init/ready.d/01-create-s3-bucket.sh`), so uploads work out
of the box with `docker compose up`.

Uploads exercise the real code path: real boto3 client, real bucket, real keys,
real presigned URLs. Nothing about the upload flow is mocked.

To poke at the bucket by hand, install
[awslocal](https://github.com/localstack/awscli-local):

```bash
pip install 'awscli-local[ver1]'
awslocal s3 ls s3://litefile-staging/efile-documents/ --recursive
```

Also make sure that `AWS_S3_ENDPOINT_URL = "http://host.docker.internal:4566"` and `AWS_ACCOUNT_ID_ENDPOINT_MODE = "disabled"` in your env.

## Filing code search

`docker compose up` also starts `code_index_worker`, which builds the filing-code
search indexes and refreshes them daily. The web container's migrations must
finish before the worker starts. Search is unavailable until a state's first
complete catalog has been indexed; opening the search dialog does not start a
build. The court lists remain usable while indexing runs.

If Compose is already running, start the worker in a terminal you control:

```bash
docker compose up code_index_worker
```

To build only Illinois once in the existing web container instead:

```bash
docker compose exec web uv run python manage.py refresh_filing_code_index --jurisdiction illinois --verbosity 2 --cache-dir /data/filing-code-cache
```

Progress lists each court as it is fetched. Wait for `indexed ... filing paths`,
then search becomes available (an open search retries automatically). Indexes
persist in the shared database volume. If a refresh
fails, the command reports the error and keeps any previous complete index.
Temporary court-service failures are retried within each request. The recurring
worker retries failed states after one minute and skips indexes refreshed within
the daily interval, including after a restart. A one-shot command still exits
with an error if its retries fail. Completed courts are checkpointed in compressed
files in the shared volume and reused for up to six hours after a failed build.

Local keyword searches use SQLite FTS5, including jurisdiction and new/existing-case
filters. The schema migration builds postings from any existing catalog; later
catalog changes maintain them automatically. Run `docker compose exec web uv run
python manage.py migrate --noinput` when updating a running stack. Compose runs
migrations automatically when starting the web container. Python tests run migrations
too, because `--nomigrations` would omit the FTS5 table and its synchronization triggers.

## Calculating fees and filing end-to-end

The EFSP proxy **downloads each document itself** from the `data_url` in the
filing payload, and it does this for a fee quote exactly as it does for a real
filing (`FilingReviewService.calculateFilingFees` runs the same deserializer,
which calls `inStream.readAllBytes()` inline). It also refuses any scheme other
than `http://` or `https://` — there is no way to POST the file bytes, and no
base64 or `data:` URI support.

A LocalStack presigned URL points at `http://localstack:4566`, which only
resolves inside the Docker network. So a hosted EFSP proxy cannot fetch your
locally uploaded document, and fee quotes fail.

By default in `efile_app/.env.example`, `EFSP_TEST_DOCUMENT_URL` points to the publicly accessible test PDF hosted in this repository:

```bash
https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/main/testing/sample_test.pdf
```

You can set `EFSP_TEST_DOCUMENT_URL` in `efile_app/.env` or your environment to any publicly readable PDF, and the app sends *that* URL to the proxy as every document's `data_url`.

```bash
# in efile_app/.env, or the environment you run compose from
EFSP_TEST_DOCUMENT_URL="https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/main/testing/sample_test.pdf"
```

What this does and does not change:

- **Unchanged:** the file is uploaded to LocalStack for real, the draft stores
  the real S3 key and URL, and the review/payment screens show the real
  document. Everything up to the EFSP call is exercised normally.
- **Changed:** only the `data_url` field in the payload sent to the proxy.

Fees are calculated from filing codes, party counts, and optional services
rather than from the document's contents, and `page_count` is taken from the
JSON payload rather than parsed out of the PDF — so a stand-in PDF returns the
same fees as the real one. It does need to be a real, fetchable PDF, because the
proxy forwards the bytes on to Tyler.

The app logs a warning on every request where a substitution happens, so a
stand-in filing is never mistaken for a real one.

### Why this cannot reach a real court

Filing a placeholder PDF in place of someone's actual document is the worst thing
this repository could do, so the stand-in is fenced in four independent ways. No
single mistake -- a stray environment variable, a dropped setting, a bad deploy --
gets past all of them, and each one fails loudly rather than quietly.

1. **`settings_dev` refuses to load on a deployed host.** `efile/settings.py` is
   a bare re-export of `settings_dev`, and `manage.py`, `wsgi.py` and `asgi.py`
   all `setdefault("DJANGO_SETTINGS_MODULE", "efile.settings")`. A deploy that
   loses `DJANGO_SETTINGS_MODULE` -- an edit to `fly.toml`'s `[env]`, a machine
   started without it -- would otherwise come up on *development* settings, with
   `DEBUG=True` and every guard below inert. `settings_dev` now raises
   `ImproperlyConfigured` at import when `FLY_APP_NAME` is present. There is no
   override flag: an escape hatch would be the same footgun again.
2. **Only `settings_dev` reads the environment variable.** `settings_staging` and
   `settings_prod` never define `EFSP_TEST_DOCUMENT_URL`, so exporting it there
   does nothing. A test asserts no other settings module starts reading it.
3. **A startup system check** (`efile.E001`, in `efile/checks.py`) fails any
   management command when the setting is non-empty while `DEBUG` is off.
   `fly.toml` runs `manage.py migrate` as its release command, so a
   misconfiguration fails the *deploy* rather than the first filing. In
   development the same check emits `efile.W001` at startup, naming the stand-in
   URL, so an active substitution is visible before anything is filed.
4. **The substitution itself refuses to run outside `DEBUG`**, raising
   `ImproperlyConfigured` rather than falling back to the real document. A
   production process holding a stand-in URL is a broken deploy and should file
   nothing at all until it is fixed.

`efile/tests/test_stand_in_document_guards.py` covers all four. The suite also
disables the stand-in for every test by default (`efile/tests/conftest.py`), so
tests run in the production-shaped configuration and a developer who has the
variable exported gets the same results as CI; tests that want the substitution
opt in with `override_settings`.

### If you need the proxy to fetch the real document

Leave `EFSP_TEST_DOCUMENT_URL` unset (empty string) and choose one of:

- Point `AWS_S3_ENDPOINT_URL` at a real dev S3 bucket. Presigned URLs are the
  production path, so this exercises exactly what ships.
- Run [EfileProxyServer](https://github.com/SuffolkLITLab/EfileProxyServer) in
  your own compose stack. It deliberately does not block private addresses, so a
  `data_url` on the Docker network works and no public ingress is needed.
