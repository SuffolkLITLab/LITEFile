import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GetCaseDataView(View):
    """API endpoint to retrieve case data from session."""

    def get(self, request):
        try:
            # Get case data from session
            case_data = request.session.get("case_data", {})

            print(f"Retrieved case data from session: {case_data}")

            return JsonResponse({"success": True, "data": case_data})

        except Exception as e:
            print(f"Error retrieving case data: {e}")
            return JsonResponse({"success": False, "error": "Server error occurred"}, status=500)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SaveCaseDataView(View):
    """API endpoint to save case data to session."""

    def post(self, request):
        try:
            data = json.loads(request.body)

            # Extract case data from form submission
            case_data = {
                "court": data.get("court", ""),
                "case_category": data.get("case_category", ""),
                "case_type": data.get("case_type", ""),
                "filing_type": data.get("filing_type", ""),
                "document_type": data.get("document_type", ""),
                "petitioner_first_name": data.get("petitioner_first_name", ""),
                "petitioner_last_name": data.get("petitioner_last_name", ""),
                "petitioner_address": data.get("petitioner_address", ""),
                "petitioner_party_type": data.get("petitioner_party_type", ""),  # Add party type
                "new_first_name": data.get("new_first_name", ""),
                "new_last_name": data.get("new_last_name", ""),
                "new_name_party_type": data.get("new_name_party_type", ""),  # Add party type
                "optional_services": data.get("optional_services", []),
            }

            # Validate required fields
            required_fields = ["court", "case_category", "case_type", "filing_type", "document_type"]
            missing_fields = [field for field in required_fields if not case_data.get(field)]

            if missing_fields:
                err_missing = f"Missing required fields: {', '.join(missing_fields)}"
                return JsonResponse({"success": False, "error": err_missing}, status=400)

            # For name change cases, validate party information
            if "name change" in case_data.get("case_type", "").lower():
                party_fields = ["petitioner_first_name", "petitioner_last_name", "new_first_name", "new_last_name"]
                missing_party_fields = [field for field in party_fields if not case_data.get(field)]

                if missing_party_fields:
                    err_party = f"Missing party information for name change case: {', '.join(missing_party_fields)}"
                    return JsonResponse({"success": False, "error": err_party}, status=400)

            # Save to session
            request.session["case_data"] = case_data
            request.session.modified = True

            print(f"Saved case data to session: {case_data}")

            return JsonResponse({"success": True, "message": "Case data saved successfully"})

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
        except Exception as e:
            print(f"Error saving case data: {e}")
            return JsonResponse({"success": False, "error": "Server error occurred"}, status=500)


# Function-based view wrapper for easy URL mapping
get_case_data = GetCaseDataView.as_view()
save_case_data = SaveCaseDataView.as_view()
