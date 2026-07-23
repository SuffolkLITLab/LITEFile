import logging
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..utils.s3_upload_handler import S3UploadHandler

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def test_s3_connection(request):
    """Test S3 connection and bucket access."""
    try:
        # A fresh handler per request, so a credential change takes effect
        # without a restart.
        s3_handler = S3UploadHandler()

        # Test S3 connection
        if s3_handler._ensure_initialized():
            # Ensure the client is initialized for type checkers
            if s3_handler.s3_client is None:
                return JsonResponse({"success": False, "error": "S3 client not initialized"}, status=500)
            response = s3_handler.s3_client.list_objects_v2(Bucket=s3_handler.bucket_name, MaxKeys=1)

            return JsonResponse(
                {
                    "success": True,
                    "message": "S3 connection successful",
                    "bucket": s3_handler.bucket_name,
                    "region": s3_handler.region_name,
                    "objects_exist": "Contents" in response,
                }
            )
        else:
            return JsonResponse({"success": False, "error": "S3 client not initialized - check AWS credentials"})

    except Exception as e:
        return JsonResponse({"success": False, "error": f"S3 connection failed: {str(e)}"})


@csrf_exempt
@require_http_methods(["POST"])
def simple_s3_upload(request):
    """Simple S3 upload that just uploads files and returns URLs."""
    try:
        logger.debug(
            "simple_s3_upload method=%s file_keys=%s post_keys=%s",
            request.method,
            list(request.FILES.keys()),
            list(request.POST.keys()),
        )

        # Handle file uploads
        uploaded_files = request.FILES.getlist("documents")

        logger.debug("simple_s3_upload found %d files", len(uploaded_files))

        if not uploaded_files:
            return JsonResponse({"success": False, "error": "No documents provided."}, status=400)

        s3_handler = S3UploadHandler()

        if not s3_handler._ensure_initialized():
            return JsonResponse(
                {"success": False, "error": "S3 not configured properly. Check AWS credentials."}, status=500
            )

        s3_upload_results = []

        # Upload all files to S3
        for i, uploaded_file in enumerate(uploaded_files):
            # Validate file
            validation_result = s3_handler.validate_file(uploaded_file, max_size_mb=10, allowed_types=[".pdf"])

            if not validation_result["valid"]:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"File validation failed for {uploaded_file.name}: {validation_result['error']}",
                    },
                    status=400,
                )

            # Prepare metadata
            file_type = "lead" if i == 0 else "supporting"
            metadata = {
                "file-type": file_type,
                "original-size": str(uploaded_file.size),
                "original-name": uploaded_file.name,
                "upload-session": str(uuid.uuid4())[:8],
            }

            # Upload to S3
            upload_result = s3_handler.upload_file(uploaded_file, file_type=file_type, metadata=metadata)

            if not upload_result["success"]:
                return JsonResponse(
                    {"success": False, "error": f"S3 upload failed for {uploaded_file.name}: {upload_result['error']}"},
                    status=500,
                )

            s3_upload_results.append(
                {
                    "original_name": uploaded_file.name,
                    "url": upload_result["url"],
                    "public_url": s3_handler.get_public_url(upload_result["key"]),
                    "key": upload_result["key"],
                    "size": upload_result["size"],
                    "type": file_type,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "message": f"Successfully uploaded {len(s3_upload_results)} file(s) to S3",
                "files": s3_upload_results,
            }
        )

    except Exception as e:
        logger.error(f"Simple S3 upload error: {e}")
        return JsonResponse({"success": False, "error": f"Upload error: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def mock_s3_upload(request):
    """Mock S3 upload for testing when AWS permissions aren't available."""
    try:
        # Handle file uploads
        uploaded_files = request.FILES.getlist("documents")

        if not uploaded_files:
            return JsonResponse({"success": False, "error": "No documents provided."}, status=400)

        mock_upload_results = []

        # Simulate S3 upload results
        for i, uploaded_file in enumerate(uploaded_files):
            # Validate file type
            if not (uploaded_file.name.lower().endswith(".pdf") or uploaded_file.content_type == "application/pdf"):
                return JsonResponse(
                    {"success": False, "error": f"Invalid file type: {uploaded_file.name}. Only PDF files allowed."},
                    status=400,
                )

            # Simulate file size validation
            max_size = 10 * 1024 * 1024  # 10MB
            if uploaded_file.size > max_size:
                return JsonResponse(
                    {"success": False, "error": f"File too large: {uploaded_file.name}. Maximum size is 10MB."},
                    status=400,
                )

            # Generate mock S3 URLs
            file_id = str(uuid.uuid4())[:8]
            file_type = "lead" if i == 0 else "supporting"

            mock_upload_results.append(
                {
                    "original_name": uploaded_file.name,
                    "url": f"https://litefile-staging.s3.amazonaws.com/efile-documents/{file_type}/{file_id}.pdf",
                    "public_url": f"https://litefile-staging.s3.amazonaws.com/efile-documents/{file_type}/{file_id}.pdf",
                    "key": f"efile-documents/{file_type}/{file_id}.pdf",
                    "size": uploaded_file.size,
                    "type": file_type,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "message": f"Mock upload: Successfully processed {len(mock_upload_results)} file(s)",
                "files": mock_upload_results,
            }
        )

    except Exception as e:
        logger.error(f"Mock S3 upload error: {e}")
        return JsonResponse({"success": False, "error": f"Upload error: {str(e)}"}, status=500)
