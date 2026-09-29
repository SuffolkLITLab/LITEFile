"""Presigned document access must stay private and use the bucket region."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.exceptions import ClientError
from django.test import override_settings

from efile.utils.s3_upload_handler import S3UploadHandler


@override_settings(
    AWS_ACCESS_KEY_ID="test-access-key",
    AWS_SECRET_ACCESS_KEY="test-secret-key",
    AWS_SESSION_TOKEN="test-session-token",
    AWS_S3_BUCKET_NAME="test-documents",
    AWS_S3_REGION_NAME="us-west-2",
    AWS_S3_ENDPOINT_URL=None,
)
def test_presigned_url_uses_configured_region_and_sigv4():
    with patch("botocore.client.BaseClient._make_api_call", return_value={}) as request:
        url = S3UploadHandler().get_public_url("efile-documents/lead/test.pdf")

    query = parse_qs(urlsplit(url).query)
    assert urlsplit(url).hostname == "test-documents.s3.us-west-2.amazonaws.com"
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Security-Token"] == ["test-session-token"]
    assert "/us-west-2/s3/aws4_request" in query["X-Amz-Credential"][0]
    request.assert_called_once_with(
        "ListObjectsV2", {"Bucket": "test-documents", "Prefix": "efile-documents/", "MaxKeys": 1}
    )


@override_settings(AWS_ACCESS_KEY_ID="", AWS_SECRET_ACCESS_KEY="", AWS_S3_BUCKET_NAME="test-documents")
def test_presigned_url_fails_closed_without_credentials():
    with pytest.raises(RuntimeError, match="S3 client not initialized"):
        S3UploadHandler().get_public_url("efile-documents/lead/test.pdf")


@override_settings(
    AWS_ACCESS_KEY_ID="test-access-key",
    AWS_SECRET_ACCESS_KEY="test-secret-key",
    AWS_S3_BUCKET_NAME="test-documents",
    AWS_S3_REGION_NAME="us-west-2",
    AWS_S3_ENDPOINT_URL="http://localhost:4566",
)
def test_localstack_presigned_url_uses_path_style():
    with patch("botocore.client.BaseClient._make_api_call", return_value={}):
        url = S3UploadHandler().get_public_url("efile-documents/lead/test.pdf")

    assert urlsplit(url).netloc == "localhost:4566"
    assert urlsplit(url).path == "/test-documents/efile-documents/lead/test.pdf"


@override_settings(
    AWS_ACCESS_KEY_ID="test-access-key",
    AWS_SECRET_ACCESS_KEY="test-secret-key",
    AWS_S3_BUCKET_NAME="test-documents",
    AWS_S3_REGION_NAME="us-west-2",
    AWS_S3_ENDPOINT_URL=None,
)
def test_presigned_url_does_not_fall_back_to_unsigned_url():
    handler = S3UploadHandler()
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "Denied"}}, "GetObject")
    with patch("botocore.client.BaseClient._make_api_call", return_value={}):
        assert handler._ensure_initialized()
    with patch.object(handler.s3_client, "generate_presigned_url", side_effect=error):
        with pytest.raises(ClientError):
            handler.get_public_url("efile-documents/lead/test.pdf")
        with pytest.raises(ClientError):
            handler._generate_file_url("efile-documents/lead/test.pdf")
