# Testing Help

For local testing, we recommend using [LocalStack](https://docs.localstack.cloud/aws/getting-started/installation/#docker-compose)
to mock S3 locally, and [awslocal](https://github.com/localstack/awscli-local)
to use it. 

LocalStack will be used through Docker, but to install `awslocal`, run the following:

```bash
pip install awscli-local[ver1]
``

You can start the S3 mock using the `docker-compose.yml` here in this folder with the following commands.

```bash
docker compose up -d
# Create a bucket with the name that should be in .env as `AWS_S3_BUCKET_NAME`. `AWS_S3_REGION_NAME` defaults to "us-east-1".
awslocal s3api create-bucket --bucket efile-form-submission-bucket
```

Also make sure that `AWS_S3_ENDPOINT_URL = "http://host.docker.internal:4566"` and `AWS_ACCOUNT_ID_ENDPOINT_MODE = "disabled"` in your env.

## Calculating fees and filing end-to-end

The EFSP proxy downloads each document itself from the `data_url` in the filing payload. A LocalStack presigned URL points to local/Docker host addresses which a remote EFSP proxy cannot reach.

By default in local development (`settings_dev.py` / `compose.yml`), `EFSP_TEST_DOCUMENT_URL` points to the publicly accessible test PDF hosted in this repository:

```bash
https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/main/testing/sample_test.pdf
```

You can override this in `efile_app/.env` or your environment if you wish to use a different publicly accessible PDF.
