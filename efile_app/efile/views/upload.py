import logging
import uuid

import requests
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..utils.case_data_utils import get_case_classification, get_case_data, get_name_sought_info, get_petitioner_info
from ..utils.config_loader import config_loader
from ..utils.s3_upload import s3_handler

logger = logging.getLogger(__name__)


def get_party_type_code_from_api(court_code, case_type_code, jurisdiction="illinois", target_party_name=None):
    """
    Fetch party type codes from the Suffolk LIT Lab API and return the appropriate code.
    """
    try:
        path = f"/jurisdictions/{jurisdiction}/codes/courts/{court_code}/case_types/{case_type_code}/party_types"
        api_url = f"{settings.EFSP_URL}{path}"

        response = requests.get(api_url, timeout=10)

        if response.status_code == 200:
            party_types = response.json()

            if target_party_name:
                # Look for a specific party type by name (case-insensitive)
                for party_type in party_types:
                    if isinstance(party_type, dict) and "name" in party_type and "code" in party_type:
                        if target_party_name.lower() in party_type["name"].lower():
                            return party_type["code"]

            # If no specific match found, return the first available party type code
            if party_types and isinstance(party_types[0], dict) and "code" in party_types[0]:
                return party_types[0]["code"]

    except Exception as e:
        logger.error(f"Failed to fetch party types from API: {e}")

    # Fallback to default codes if API call fails
    return None


def determine_party_type_for_new_case(case_data):
    """
    Determine the appropriate party type for a new case.
    This fetches actual party type codes from the API.
    """
    court_code = case_data.get("court")
    case_type_code = case_data.get("case_type")
    case_type = case_data.get("case_type", "").lower()

    if not court_code or not case_type_code:
        logger.warning("Missing court or case_type for party type determination")
        return "PET"  # Default fallback code for petitioner

    # Determine target party type name based on case type
    target_party_name = None

    if "name change" in case_type:
        target_party_name = "petitioner"
    elif "civil" in case_type:
        target_party_name = "plaintiff"
    elif "family" in case_type:
        target_party_name = "petitioner"
    elif "probate" in case_type:
        target_party_name = "petitioner"
    else:
        target_party_name = "petitioner"

    # Get the actual party type code from API
    party_code = get_party_type_code_from_api(court_code, case_type_code, target_party_name=target_party_name)

    # Fallback codes if API call fails
    if not party_code:
        if target_party_name == "plaintiff":
            return "PLA"
        elif target_party_name == "petitioner":
            return "PET"
        else:
            return "PET"

    return party_code


def determine_party_type_for_existing_case(case_data):
    """
    Determine the appropriate party type when responding to an existing case.
    This fetches actual party type codes from the API.
    """
    court_code = case_data.get("court")
    case_type_code = case_data.get("case_type")
    case_type = case_data.get("case_type", "").lower()
    filing_type = case_data.get("filing_type", "").lower()

    if not court_code or not case_type_code:
        logger.warning("Missing court or case_type for party type determination")
        return "DEF"  # Default fallback code

    # Determine target party type name based on case and filing type
    target_party_name = None

    if "criminal" in case_type:
        target_party_name = "defendant"
    elif "civil" in case_type or "family" in case_type:
        if "answer" in filing_type or "response" in filing_type:
            target_party_name = "respondent"
        else:
            target_party_name = "defendant"
    elif "probate" in case_type:
        target_party_name = "interested party"
    else:
        target_party_name = "defendant"

    # Get the actual party type code from API
    party_code = get_party_type_code_from_api(court_code, case_type_code, target_party_name=target_party_name)

    # Fallback codes if API call fails
    if not party_code:
        if target_party_name == "defendant":
            return "DEF"
        elif target_party_name == "respondent":
            return "RES"
        elif target_party_name == "interested party":
            return "INT"
        else:
            return "DEF"

    return party_code


def efile_upload(request, jurisdiction):
    """Upload view for document submission and filing creation."""

    # Check if user is authenticated first
    if not request.user.is_authenticated:
        return redirect("efile_login", jurisdiction=jurisdiction)

    # Get case data from session
    case_data = get_case_data(request)

    # If no case data exists, redirect back to options page
    if not case_data:
        messages.error(request, "Please complete the case details first.")
        return redirect("efile_options", jurisdiction=jurisdiction)

    # Get organized case information
    petitioner_info = get_petitioner_info(request)
    name_sought_info = get_name_sought_info(request)
    case_classification = get_case_classification(request)

    # Use friendly names if available, otherwise fallback to raw values
    friendly_case_type = case_data.get("case_type_name", case_classification["case_type"])
    friendly_filing_type = case_data.get("filing_type_name", case_classification["filing_type"])
    friendly_court = case_data.get("court_name", case_classification["court"])

    jurisdiction_config = config_loader.get_short_jurisdiction_config(jurisdiction)

    context = {
        "jurisdiction": jurisdiction,
        "jurisdiction_config": jurisdiction_config,
        "case_data": case_data,
        "petitioner_info": petitioner_info,
        "name_sought_info": name_sought_info,
        "case_classification": case_classification,
        "case_type": friendly_case_type,
        "filing_type": friendly_filing_type,
        "court": friendly_court,
        "case_type_raw": case_classification["case_type"],
        "category_type_raw": case_classification["case_category"],
        "filing_type_raw": case_classification["filing_type"],
        "court_raw": case_classification["court"],
    }

    return render(request, "efile/upload.html", context)


@csrf_exempt
@require_http_methods(["POST"])
def create_filing(request):
    """Create a filing with Suffolk LIT Lab API using collected case data."""

    try:
        # Get case data from session
        case_data = get_case_data(request)

        if not case_data:
            return JsonResponse(
                {"success": False, "error": "No case data found. Please complete the expert form first."}, status=400
            )

        # Get auth tokens
        auth_tokens = request.session.get("auth_tokens")
        if not auth_tokens or "token" not in auth_tokens:
            return JsonResponse(
                {"success": False, "error": "Authentication required. Please log in first."}, status=401
            )

        # Transform case data to Suffolk API payload format
        filing_payload = transform_case_data_to_filing_payload(case_data, request)

        # Make POST request to Suffolk LIT Lab filing API
        path = "/filings/"
        api_url = f"{settings.EFSP_URL}{path}"

        headers = {"Authorization": f"Bearer {auth_tokens['token']}", "Content-Type": "application/json"}

        # Safe pre-request logging
        logger.debug(
            "POST %s with headers keys=%s payload keys=%s",
            api_url,
            list(headers.keys()),
            list(filing_payload.keys()),
        )
        response = requests.post(api_url, headers=headers, json=filing_payload, timeout=30)
        logger.debug(
            "Create filing response: status=%s content_type=%s",
            response.status_code,
            response.headers.get("Content-Type"),
        )

        if response.status_code == 201:
            # Filing created successfully
            filing_data = response.json()

            # Save filing ID to session for future reference
            request.session["current_filing_id"] = filing_data.get("id")
            request.session.modified = True

            return JsonResponse(
                {
                    "success": True,
                    "filing_id": filing_data.get("id"),
                    "message": "Filing created successfully",
                    "data": filing_data,
                }
            )
        else:
            # API error
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = error_json.get("detail", error_json)
            except ValueError:
                pass

            return JsonResponse(
                {
                    "success": False,
                    "error": f"Filing creation failed: {error_detail}",
                    "status_code": response.status_code,
                },
                status=response.status_code,
            )

    except requests.RequestException as e:
        return JsonResponse({"success": False, "error": f"Network error: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Unexpected error: {str(e)}"}, status=500)


def transform_case_data_to_filing_payload(case_data, request=None):
    """
    Transform collected case data into Suffolk LIT Lab API filing payload format.
    """

    # Base filing payload structure
    payload = {
        "jurisdiction": "illinois",
        "court": case_data.get("court"),
        "category": case_data.get("case_category"),
        "case_type": case_data.get("case_type"),
        "filing_type": case_data.get("filing_type"),
        "document_type": case_data.get("document_type"),
        "parties": [],
        "optional_services": case_data.get("optional_services", []),
    }

    # Add petitioner party if this is a name change case
    if "name change" in case_data.get("case_type", "").lower():
        # Add petitioner
        if case_data.get("petitioner_first_name") or case_data.get("petitioner_last_name"):
            # Use party type from session data, or determine it from API
            party_type = case_data.get("petitioner_party_type")
            if not party_type:
                party_type = determine_party_type_for_new_case(case_data)

            petitioner = {
                "party_type": party_type,
                "name": {
                    "first": case_data.get("petitioner_first_name", ""),
                    "last": case_data.get("petitioner_last_name", ""),
                    "full": (
                        f"{case_data.get('petitioner_first_name', '')} {case_data.get('petitioner_last_name', '')}"
                    ).strip(),
                },
                "address": case_data.get("petitioner_address", ""),
                "role": "Petitioner",  # Keep role as readable text
            }
            payload["parties"].append(petitioner)
    else:
        # For non-name change cases, still add the party information if available
        if case_data.get("first_name") or case_data.get("last_name"):
            # Determine party type based on existing case status
            existing_case = None
            if request:
                existing_case = request.session.get("existing_case")

            # Also check if existing_case is stored in case_data
            if not existing_case:
                existing_case = case_data.get("existing_case")

            if existing_case == "yes":
                # When responding to existing case, use intelligent party type determination
                party_type = case_data.get("party_type") or determine_party_type_for_existing_case(case_data)
            else:
                # For new cases, use intelligent party type determination
                party_type = case_data.get("party_type") or determine_party_type_for_new_case(case_data)

            # Determine role name for display (keep as readable text)
            if existing_case == "yes":
                role_name = "Defendant" if "DEF" in party_type else "Respondent" if "RES" in party_type else "Party"
            else:
                role_name = "Petitioner" if "PET" in party_type else "Plaintiff" if "PLA" in party_type else "Party"

            party = {
                "party_type": party_type,
                "name": {
                    "first": case_data.get("first_name", ""),
                    "last": case_data.get("last_name", ""),
                    "full": (f"{case_data.get('first_name', '')} {case_data.get('last_name', '')}").strip(),
                },
                "address": case_data.get("address", ""),
                "role": role_name,
            }
            payload["parties"].append(party)

        # Add name sought information as additional case details
        if case_data.get("new_first_name") or case_data.get("new_last_name"):
            payload["name_change_details"] = {
                "new_name": {
                    "first": case_data.get("new_first_name", ""),
                    "last": case_data.get("new_last_name", ""),
                    "full": (f"{case_data.get('new_first_name', '')} {case_data.get('new_last_name', '')}").strip(),
                }
            }

    # Add case metadata
    payload["metadata"] = {
        "created_via": "illinois_efile_system",
        "case_classification": {
            "court": case_data.get("court"),
            "category": case_data.get("case_category"),
            "case_type": case_data.get("case_type"),
            "filing_type": case_data.get("filing_type"),
            "document_type": case_data.get("document_type"),
        },
    }

    return payload


@csrf_exempt
@require_http_methods(["POST"])
def upload_documents(request):
    """Handle document uploads using S3, then submit to Suffolk API."""

    try:
        # Get current filing ID from session
        filing_id = request.session.get("current_filing_id")

        if not filing_id:
            return JsonResponse(
                {"success": False, "error": "No active filing found. Please create a filing first."}, status=400
            )

        # Get auth tokens
        auth_tokens = request.session.get("auth_tokens")
        if not auth_tokens or "token" not in auth_tokens:
            return JsonResponse({"success": False, "error": "Authentication required."}, status=401)

        # Handle file uploads
        uploaded_files = request.FILES.getlist("documents")
        file_type = request.POST.get("file_type", "document")

        if not uploaded_files:
            return JsonResponse({"success": False, "error": "No documents provided."}, status=400)

        s3_upload_results = []

        # First upload all files to S3
        for uploaded_file in uploaded_files:
            # Validate file
            validation_result = s3_handler.validate_file(
                uploaded_file,
                max_size_mb=10,
                allowed_types=[".pdf"],  # Only PDFs for efile
            )

            if not validation_result["valid"]:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"File validation failed for {uploaded_file.name}: {validation_result['error']}",
                    },
                    status=400,
                )

            # Prepare metadata
            metadata = {
                "file-type": file_type,
                "filing-id": str(filing_id),
                "original-size": str(uploaded_file.size),
                "original-name": uploaded_file.name,
            }

            # Upload to S3
            upload_result = s3_handler.upload_file(uploaded_file, file_type=file_type, metadata=metadata)

            logger.debug("S3 upload result: %s", upload_result)

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
                }
            )
        logger.debug("S3 upload results count=%d", len(s3_upload_results))

        # Now submit the S3 URLs to Suffolk API
        submitted_documents = []

        for s3_result in s3_upload_results:
            # Submit document URL to Suffolk API instead of uploading file
            document_payload = {
                "filing_id": filing_id,
                "document_url": s3_result["public_url"],  # Use public S3 URL
                "document_name": s3_result["original_name"],
                "document_size": s3_result["size"],
            }

            path = f"/filings/{filing_id}/documents/"
            api_url = f"{settings.EFSP_URL}{path}"

            headers = {"Authorization": f"Bearer {auth_tokens['token']}", "Content-Type": "application/json"}

            # Safe pre-request logging
            logger.debug(
                "POST %s with headers keys=%s payload keys=%s",
                api_url,
                list(headers.keys()),
                list(document_payload.keys()),
            )
            response = requests.post(api_url, headers=headers, json=document_payload, timeout=60)
            logger.debug(
                "Submit document response: status=%s content_type=%s",
                response.status_code,
                response.headers.get("Content-Type"),
            )

            if response.status_code == 201:
                document_data = response.json()
                document_data["s3_url"] = s3_result["public_url"]
                document_data["s3_key"] = s3_result["key"]
                submitted_documents.append(document_data)
            else:
                # If submission fails, we should clean up the S3 file
                logger.warning(f"Failed to submit document to Suffolk API, cleaning up S3 file: {s3_result['key']}")
                s3_handler.delete_file(s3_result["key"])

                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Failed to submit {s3_result['original_name']} to Suffolk API: {response.text}",
                    },
                    status=response.status_code,
                )

        return JsonResponse(
            {
                "success": True,
                "message": f"Successfully uploaded {len(submitted_documents)} document(s)",
                "documents": submitted_documents,
                "s3_uploads": s3_upload_results,
            }
        )

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return JsonResponse({"success": False, "error": f"Upload error: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def test_s3_connection(request):
    """Test S3 connection and bucket access."""
    try:
        # Reinitialize the global handler to pick up the corrected credentials
        global s3_handler
        from ..utils.s3_upload import S3UploadHandler

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

        # Reinitialize S3 handler
        global s3_handler
        from ..utils.s3_upload import S3UploadHandler

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
                    "url": f"https://forms-mvp-xf6361.s3.amazonaws.com/efile-documents/{file_type}/{file_id}.pdf",
                    "public_url": f"https://forms-mvp-xf6361.s3.amazonaws.com/efile-documents/{file_type}/{file_id}.pdf",
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
