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
