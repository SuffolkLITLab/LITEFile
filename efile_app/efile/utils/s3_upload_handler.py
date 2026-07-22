"""
S3 Upload utilities for handling document uploads to AWS S3
"""

import logging
import mimetypes
import re
import time
import uuid
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


class S3UploadHandler:
    """Handles file uploads to AWS S3 and generates secure URLs"""

    def __init__(self):
        """Initialize S3 upload handler with AWS configuration."""
        self.s3_client = None
        self.credentials_checked = False

    def _ensure_initialized(self):
        """Ensure S3 client is initialized - check credentials dynamically."""
        if self.s3_client is not None:
            return True

        # Get credentials from Django settings
        self.access_key_id = getattr(settings, "AWS_ACCESS_KEY_ID", "")
        self.secret_access_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", "")
        self.bucket_name = getattr(settings, "AWS_S3_BUCKET_NAME", "")
        self.region_name = getattr(settings, "AWS_S3_REGION_NAME", "us-east-1")
        self.s3_endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", None)

        # Check for required credentials
        if not all([self.access_key_id, self.secret_access_key, self.bucket_name]):
            if not self.credentials_checked:
                logger.warning("AWS credentials not fully configured")
                logger.debug(
                    "AWS credential presence - access_key_id: %s, secret_access_key: %s, bucket_name: %s",
                    "Set" if self.access_key_id else "Missing",
                    "Set" if self.secret_access_key else "Missing",
                    "Set" if self.bucket_name else "Missing",
                )
                self.credentials_checked = True
            return False
        else:
            self._initialize_s3_client()
            return self.s3_client is not None

    def _initialize_s3_client(self):
        """Initialize the S3 client and verify bucket access."""
        try:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region_name,
                endpoint_url=self.s3_endpoint_url,
            )

            # Test connection by attempting to list objects (limited test)
            try:
                self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1)
                logger.info("S3 connection successful to bucket: %s", self.bucket_name)
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "403":
                    logger.warning(
                        "Access denied to S3 bucket %s. Check credentials and permissions.", self.bucket_name
                    )
                elif error_code == "404":
                    logger.warning("S3 bucket %s not found.", self.bucket_name)
                else:
                    logger.warning("S3 bucket access test failed on %s: %s", self.bucket_name, e)
                # Don't raise exception here, allow the client to be initialized
                # so we can test credentials later with proper error handling

        except Exception as e:
            logger.error("Failed to initialize S3 client: %s", e)
            self.s3_client = None

    def upload_file(self, file_obj, file_type="document", metadata=None):
        """
        Upload a file to S3 and return the URL

        Args:
            file_obj: Django UploadedFile object
            file_type: Type of file (e.g., 'lead_document', 'supporting_document')
            metadata: Optional metadata dictionary

        Returns:
            dict: {
                'success': bool,
                'url': str,
                'key': str,
                'error': str (if failed)
            }
        """
        if not self._ensure_initialized():
            return {"success": False, "error": "S3 client not initialized - check AWS credentials"}

        try:
            # Generate unique filename
            file_extension = self._get_file_extension(file_obj.name)
            unique_filename = f"{uuid.uuid4().hex}{file_extension}"

            # Create S3 key with folder structure
            s3_key = f"efile-documents/{file_type}/{unique_filename}"

            # Prepare metadata
            s3_metadata = {
                "original-filename": quote(file_obj.name),
                "file-type": file_type,
                "upload-timestamp": str(int(uuid.uuid1().time)),
            }

            if metadata:
                s3_metadata.update(metadata)

            # Determine content type
            content_type = file_obj.content_type or mimetypes.guess_type(file_obj.name)[0] or "application/octet-stream"

            # Upload file
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": s3_metadata,
                    # No ACL specified - bucket policy controls access
                },
            )

            # Generate the URL that can be used for efile submission
            file_url = self._generate_file_url(s3_key)

            logger.info(f"Successfully uploaded file {file_obj.name} to S3: {s3_key}")

            return {
                "success": True,
                "url": file_url,
                "key": s3_key,
                "bucket": self.bucket_name,
                "filename": file_obj.name,
                "size": file_obj.size,
                "content_type": content_type,
            }

        except ClientError as e:
            error_msg = f"Failed to upload file to S3: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error during S3 upload: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def _generate_file_url(self, s3_key, expiration=3600):
        """
        Generate a presigned URL for the uploaded file

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            str: Presigned URL
        """
        try:
            # For efile submission, we might need a longer-lived URL
            # or use a different approach depending on Suffolk's requirements
            presigned_url = self.s3_client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket_name, "Key": s3_key}, ExpiresIn=expiration
            )

            logger.debug("Generated presigned URL: %s for key: %s", presigned_url, s3_key)

            return presigned_url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            # Fallback to public URL if needed
            return f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{s3_key}"

    def get_public_url(self, s3_key, expiration=604800):  # 7 days default
        """
        Get a presigned URL for an S3 object (for efile submission)
        Uses presigned URLs since bucket policy makes files private
        """
        local_url = self.get_local_public_url(s3_key)
        if local_url:
            return local_url

        if self.s3_client:
            try:
                return self.s3_client.generate_presigned_url(
                    "get_object", Params={"Bucket": self.bucket_name, "Key": s3_key}, ExpiresIn=expiration
                )
            except ClientError as e:
                logger.error(f"Failed to generate presigned URL for public access: {e}")

        # Fallback to direct URL (will return 403 with current bucket policy)
        return f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{s3_key}"

    @classmethod
    def get_local_public_url(cls, s3_key):
        """Return a public proxy URL for a local S3 key, if configured."""
        local_tunnel_url = cls._get_local_tunnel_url()
        if not local_tunnel_url:
            return None
        return f"{local_tunnel_url}/api/public-upload/{quote(s3_key, safe='/')}"

    @staticmethod
    def _get_local_tunnel_url():
        """Read the automatic local-development tunnel URL.

        cloudflared writes the URL after it starts. Waiting here makes the
        first upload reliable even if it happens while the tunnel is booting.
        The shared log setting is absent outside local Docker development.
        """
        log_path = getattr(settings, "LOCAL_PUBLIC_UPLOAD_TUNNEL_LOG", "")
        if not log_path:
            return None

        wait_seconds = max(0, getattr(settings, "LOCAL_PUBLIC_UPLOAD_WAIT_SECONDS", 30))
        deadline = time.monotonic() + wait_seconds
        tunnel_pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)

        while True:
            try:
                with open(log_path, encoding="utf-8") as log_file:
                    log_contents = log_file.read()
                # A named Docker volume keeps the log across container
                # restarts. Ignore the previous tunnel until cloudflared has
                # announced a new one.
                latest_start = log_contents.rfind("Requesting new quick Tunnel")
                current_log = log_contents[latest_start:] if latest_start != -1 else log_contents
                matches = tunnel_pattern.findall(current_log)
                if matches:
                    return matches[-1].rstrip("/")
            except FileNotFoundError:
                pass
            except OSError as error:
                logger.warning("Could not read local public upload tunnel log: %s", error)
                return None

            if time.monotonic() >= deadline:
                logger.error(
                    "Local public upload tunnel did not become ready within %ss",
                    wait_seconds,
                )
                return None
            time.sleep(0.25)

    def delete_file(self, s3_key):
        """
        Delete a file from S3

        Args:
            s3_key: S3 object key

        Returns:
            dict: {'success': bool, 'error': str (if failed)}
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Successfully deleted file from S3: {s3_key}")
            return {"success": True}

        except ClientError as e:
            error_msg = f"Failed to delete file from S3: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def _get_file_extension(self, filename):
        """Extract file extension from filename"""
        if "." in filename:
            return "." + filename.rsplit(".", 1)[1].lower()
        return ""

    def validate_file(self, file_obj, max_size_mb=10, allowed_types=None):
        """
        Validate uploaded file

        Args:
            file_obj: Django UploadedFile object
            max_size_mb: Maximum file size in MB
            allowed_types: List of allowed file extensions

        Returns:
            dict: {'valid': bool, 'error': str (if invalid)}
        """
        if allowed_types is None:
            allowed_types = [".pdf", ".doc", ".docx", ".txt"]

        # Check file size
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_obj.size > max_size_bytes:
            return {"valid": False, "error": f"File size exceeds {max_size_mb}MB limit"}

        # Check file type
        file_extension = self._get_file_extension(file_obj.name)
        if file_extension not in allowed_types:
            return {
                "valid": False,
                "error": f"File type {file_extension} not allowed. Allowed types: {', '.join(allowed_types)}",
            }

        # Additional validation for PDF files
        if file_extension == ".pdf":
            # You could add PDF-specific validation here
            pass

        return {"valid": True}


# Global instance
s3_handler = S3UploadHandler()
