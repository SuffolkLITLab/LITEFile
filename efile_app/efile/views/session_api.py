import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..utils.zip_to_county_il import get_county_by_zip


@csrf_exempt
@require_http_methods(["POST"])
def save_form_data_to_session(request):
    """Save form data (including petitioner contact info) to Django session and derive county from zip."""
    try:
        data = json.loads(request.body)
        form_data = data.get("data", {})

        # Start from existing case_data so we don't clobber other fields
        case_data = request.session.get("case_data", {})

        # Update case_data fields with provided form values (preserve existing when not provided)
        case_data.update(
            {
                "court": form_data.get("court", case_data.get("court", "")),
                "case_category": form_data.get("case_category", case_data.get("case_category", "")),
                "case_type": form_data.get("case_type", case_data.get("case_type", "")),
                "filing_type": form_data.get("filing_type", case_data.get("filing_type", "")),
                "document_type": form_data.get("document_type", case_data.get("document_type", "")),
                # simplified contact/address fields
                "first_name": form_data.get("first_name", case_data.get("first_name", "")),
                "last_name": form_data.get("last_name", case_data.get("last_name", "")),
                "address": form_data.get("address", case_data.get("address", "")),
                "address_line2": form_data.get("address_line2", case_data.get("address_line2", "")),
                "city": form_data.get("city", case_data.get("city", "")),
                "state": form_data.get("state", case_data.get("state", "")),
                "zip": form_data.get("zip", case_data.get("zip", "")),
                "email": form_data.get("email", case_data.get("email", "")),
                "phone": form_data.get("phone", case_data.get("phone", "")),
                # optional services and friendly names
                "optional_services": form_data.get("optional_services", case_data.get("optional_services", [])),
                "court_name": form_data.get("court_name", case_data.get("court_name", "")),
                "case_category_name": form_data.get("case_category_name", case_data.get("case_category_name", "")),
                "case_type_name": form_data.get("case_type_name", case_data.get("case_type_name", "")),
                "filing_type_name": form_data.get("filing_type_name", case_data.get("filing_type_name", "")),
                "document_type_name": form_data.get("document_type_name", case_data.get("document_type_name", "")),
            }
        )

        # Add all dynamic fields that might be present in the form data
        # This includes petitioner information, name change details, etc.
        dynamic_fields = [
            "petitioner_first_name",
            "petitioner_last_name",
            "petitioner_address",
            "petitioner_phone",
            "petitioner_email",
            "new_first_name",
            "new_last_name",
            "reason_for_change",
            "minor_first_name",
            "minor_last_name",
            "parent_first_name",
            "parent_last_name",
            "guardian_first_name",
            "guardian_last_name",
        ]

        for field in dynamic_fields:
            if field in form_data:
                case_data[field] = form_data[field]

        # Also save any other fields that might be dynamically added but not in our predefined list
        for key, value in form_data.items():
            if key not in case_data and value:  # Only add if not already handled and has a value
                case_data[key] = value

        # Try to derive county from zip code and save it
        zip_code = (
            case_data.get("zip") or case_data.get("zip_code") or form_data.get("zip") or form_data.get("zip_code", "")
        )
        if zip_code:
            try:
                county = get_county_by_zip(zip_code)
                if county:
                    # Save simplified county key and keep petitioner_county for backward compatibility
                    case_data["county"] = county
                    case_data["petitioner_county"] = county
            except Exception:
                # If mapping fails, ignore and continue
                pass

        # Persist to session
        request.session["case_data"] = case_data
        request.session.modified = True

        return JsonResponse({"success": True, "message": "Case data saved to session"})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_upload_data_to_session(request):
    """Save upload data and file information to Django session for review."""
    try:
        data = json.loads(request.body)

        upload_data = {
            "files": data.get("files", {}),
            "options": data.get("options", {}),
        }

        # Save to session
        request.session["upload_data"] = upload_data
        request.session.modified = True

        return JsonResponse({"success": True, "message": "Upload data saved to session"})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_http_methods(["GET"])
def get_upload_data_from_session(request):
    """Get upload data from Django session."""
    upload_data = request.session.get("upload_data", {})
    return JsonResponse(upload_data, safe=False)


@csrf_exempt
@require_http_methods(["POST"])
def submit_final_filing(request):
    """Handle final filing submission after user has reviewed all information."""
    try:
        data = json.loads(request.body)

        if not data.get("confirm_submission"):
            return JsonResponse({"success": False, "error": "Submission confirmation is required"}, status=400)

        # Get all data from session
        case_data = request.session.get("case_data", {})
        upload_data = request.session.get("upload_data", {})

        if not case_data:
            return JsonResponse(
                {
                    "success": False,
                    "error": "No case data found in session. Please go back and resubmit your case information.",
                },
                status=400,
            )

        if not upload_data or not upload_data.get("files"):
            return JsonResponse(
                {
                    "success": False,
                    "error": "No upload data found in session. Please go back and resubmit your documents.",
                },
                status=400,
            )

        # TODO: Integrate with actual efile API submission
        # This is where you would call the Suffolk LIT Lab efile API
        # to actually submit the case with all the collected data

        # For now, simulate successful submission
        # In production, you'd replace this with actual API calls

        # Clear session data after successful submission
        if "case_data" in request.session:
            del request.session["case_data"]
        if "upload_data" in request.session:
            del request.session["upload_data"]
        request.session.modified = True

        return JsonResponse(
            {
                "success": True,
                "message": "Filing submitted successfully",
                "redirect_url": "/filing-confirmation/",
                "case_id": "TEMP_" + str(hash(str(case_data)))[:8],  # Temporary case ID
            }
        )

    except (json.JSONDecodeError, Exception) as e:
        return JsonResponse({"success": False, "error": f"An error occurred during submission: {str(e)}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def clear_session_data(request):
    """Clear all session data for testing purposes."""
    request.session.flush()
    return JsonResponse({"success": True, "message": "Session data cleared"})


@require_http_methods(["GET"])
def debug_session_data(request):
    """Debug endpoint to view session contents."""
    session_data = {
        "case_data": request.session.get("case_data", {}),
        "upload_data": request.session.get("upload_data", {}),
        "session_key": request.session.session_key,
        "session_items": dict(request.session.items()),
    }
    return JsonResponse(session_data, safe=False)
