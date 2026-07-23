#!/bin/bash

set -e

awslocal s3api create-bucket \
  --bucket "${AWS_S3_BUCKET_NAME:-litefile-staging}" \
  --region "${AWS_DEFAULT_REGION:-us-east-1}" \
  2>/dev/null || true
