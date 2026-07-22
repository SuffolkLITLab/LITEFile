# Testing Help

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
awslocal s3 ls s3://forms-mvp-xf6361/efile-documents/ --recursive
```

Also make sure that `AWS_S3_ENDPOINT_URL = "http://host.docker.internal:4566"` and `AWS_ACCOUNT_ID_ENDPOINT_MODE = "disabled"` in your env.

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

The setting is defined in `settings_dev.py` only. `settings_staging` and
`settings_prod` never read it, so no environment variable can enable this
outside local development.

### If you need the proxy to fetch the real document

Leave `EFSP_TEST_DOCUMENT_URL` unset (empty string) and choose one of:

- Point `AWS_S3_ENDPOINT_URL` at a real dev S3 bucket. Presigned URLs are the
  production path, so this exercises exactly what ships.
- Run [EfileProxyServer](https://github.com/SuffolkLITLab/EfileProxyServer) in
  your own compose stack. It deliberately does not block private addresses, so a
  `data_url` on the Docker network works and no public ingress is needed.
