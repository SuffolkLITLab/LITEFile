import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
import json
import requests
from ..utils.zip_to_county_il import get_county_by_zip


def get_party_type_code_from_api(court_code, case_type_code, jurisdiction="illinois", target_party_name=None):
    """
    Fetch party type codes from the Suffolk LIT Lab API and return the appropriate code.
    """
    try:
        api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court_code}/case_types/{case_type_code}/party_types"
        
        print(f"Fetching party types from: {api_url}")
        print(f"Looking for target party name: {target_party_name}")
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            party_types = response.json()
            print(f"API returned {len(party_types)} party types:")
            for pt in party_types:
                print(f"  - {pt.get('name', 'No name')} ({pt.get('code', 'No code')})")
            
            if target_party_name:
                # Look for a specific party type by name (case-insensitive)
                target_lower = target_party_name.lower()
                print(f"Searching for target: '{target_lower}'")
                
                for party_type in party_types:
                    if isinstance(party_type, dict) and "name" in party_type and "code" in party_type:
                        party_name_lower = party_type["name"].lower()
                        print(f"  Checking: '{party_name_lower}' contains '{target_lower}'?")
                        
                        # Improved matching - check for exact words, not just substrings
                        if (target_lower in party_name_lower or 
                            party_name_lower in target_lower or
                            any(word in party_name_lower for word in target_lower.split()) or
                            any(word in target_lower for word in party_name_lower.split())):
                            print(f"  Found match: {party_type['name']} ({party_type['code']})")
                            return party_type["code"]
            
            # If no specific match found, return the first available party type code
            if party_types and isinstance(party_types[0], dict) and "code" in party_types[0]:
                first_code = party_types[0]["code"]
                print(f"No specific match found, using first party type: {party_types[0].get('name', 'Unknown')} ({first_code})")
                return first_code
        else:
            print(f"API request failed with status: {response.status_code}")
                
    except Exception as e:
        print(f"Failed to fetch party types from API: {e}")
    
    # Fallback to default codes if API call fails
    print("API call failed, returning None for fallback handling")
    return None


def determine_party_type_for_existing_case(case_data):
    """
    Determine the appropriate party type when responding to an existing case.
    This fetches actual party type codes from the API.
    """
    court_code = case_data.get('court')
    case_type_code = case_data.get('case_type')
    case_type = case_data.get('case_type', '').lower()
    filing_type = case_data.get('filing_type', '').lower()
    
    print(f"Determining party type for existing case:")
    print(f"  Court: {court_code}")
    print(f"  Case type code: {case_type_code}")
    print(f"  Case type: {case_type}")
    print(f"  Filing type: {filing_type}")
    
    if not court_code or not case_type_code:
        print("Missing court or case_type for party type determination")
        return 'DEF'  # Default fallback code
    
    # Determine target party type name based on case and filing type
    target_party_name = None
    
    if 'criminal' in case_type:
        target_party_name = 'defendant'
    elif 'civil' in case_type or 'family' in case_type:
        if 'answer' in filing_type or 'response' in filing_type:
            target_party_name = 'respondent'
        else:
            target_party_name = 'defendant'
    elif 'probate' in case_type:
        target_party_name = 'interested party'
    else:
        target_party_name = 'defendant'
    
    print(f"  Determined target party name: {target_party_name}")
    
    # Get the actual party type code from API
    party_code = get_party_type_code_from_api(court_code, case_type_code, target_party_name=target_party_name)
    
    print(f"API returned party code: {party_code}")
    
    # Fallback codes if API call fails
    if not party_code:
        print("Using fallback codes since API call failed")
        if target_party_name == 'defendant':
            fallback = 'DEF'
        elif target_party_name == 'respondent':
            fallback = 'RES'
        elif target_party_name == 'interested party':
            fallback = 'INT'
        else:
            fallback = 'DEF'
        print(f"Fallback code: {fallback}")
        return fallback
    
    print(f"Using API code: {party_code}")
    return party_code


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
        print(f"Received POST request to save upload data")
        print(f"Request body: {request.body.decode('utf-8')}")
        
        data = json.loads(request.body)
        print(f"Parsed data: {data}")

        upload_data = {
            "files": data.get("files", {}),
            "options": data.get("options", {}),
            # Lead document filing information
            "lead_filing_type": data.get("lead_filing_type", ""),
            "lead_filing_type_name": data.get("lead_filing_type_name", ""),
            "lead_document_type": data.get("lead_document_type", ""),
            "lead_document_type_name": data.get("lead_document_type_name", ""),
            "lead_filing_component": data.get("lead_filing_component", ""),
            "lead_filing_component_name": data.get("lead_filing_component_name", ""),
            # Supporting documents filing information
            "supporting_documents": data.get("supporting_documents", [])
        }

        print(f"Processed upload data: {upload_data}")

        # Save to session
        request.session["upload_data"] = upload_data
        request.session.modified = True

        print(f"Saved upload data to session successfully")
        return JsonResponse({"success": True, "message": "Upload data saved to session"})

    except Exception as e:
        print(f"Error saving upload data to session: {str(e)}")
        import traceback
        traceback.print_exc()
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
        case_data = request.session.get('case_data', {})
        upload_data = request.session.get('upload_data', {})
        auth_tokens = request.session.get('auth_tokens', {})
        
        print('Debug - Session data:')
        print(f'  - case_data keys: {list(case_data.keys()) if case_data else "Empty"}')
        print(f'  - upload_data keys: {list(upload_data.keys()) if upload_data else "Empty"}')
        print(f'  - auth_tokens keys: {list(auth_tokens.keys()) if auth_tokens else "Empty"}')
        
        if not case_data:
            return JsonResponse({
                'success': False,
                'error': 'No case data found in session. Please go back and resubmit your case information.',
                'debug_info': 'Session case_data is empty'
            }, status=400)
        
        if not upload_data or not upload_data.get('files'):
            return JsonResponse({
                'success': False,
                'error': 'No upload data found in session. Please go back and resubmit your documents.',
                'debug_info': f'Upload data: {upload_data}'
            }, status=400)
        
        # Extract efile_data from the request
        efile_data = data.get('efile_data', {})
        if not efile_data:
            return JsonResponse({
                'success': False,
                'error': 'No efile data provided in request'
            }, status=400)
        
        # Log the complete request data for debugging
        print('Complete request data received:')
        print(f'  - confirm_submission: {data.get("confirm_submission")}')
        print(f'  - efile_data keys: {list(efile_data.keys()) if isinstance(efile_data, dict) else "Not a dict"}')
        print(f'  - efile_data: {json.dumps(efile_data, indent=2)}')
        
        # Validate required fields in efile_data
        required_fields = ['al_court_bundle']  # Based on typical Suffolk API requirements
        missing_fields = [field for field in required_fields if field not in efile_data]
        if missing_fields:
            return JsonResponse({
                'success': False,
                'error': f'Missing required fields in efile_data: {missing_fields}'
            }, status=400)
        
        # Get jurisdiction and court info from case data
        jurisdiction_id = case_data.get('jurisdiction_id', 'illinois')  # Default to illinois
        court_id = case_data.get('court', '')
        
        if not court_id:
            return JsonResponse({
                'success': False,
                'error': 'Court ID is required for filing submission'
            }, status=400)
        
        # Construct the Suffolk LIT Lab API endpoint
        api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction_id}/filingreview/courts/{court_id}/filings"
        
        # Make the API call to Suffolk LIT Lab
        import requests
        
        try:
            # Get API key from Django settings
            api_key = getattr(settings, 'SUFFOLK_EFILE_API_KEY', '')
            
            # Get Tyler token from session (similar to auth_views.py)
            auth_tokens = request.session.get('auth_tokens', {})
            tyler_token = (auth_tokens.get(f'TYLER-TOKEN-{jurisdiction_id.upper()}') or 
                          auth_tokens.get(f'tyler_token_{jurisdiction_id}') or
                          auth_tokens.get(f'tyler-token-{jurisdiction_id}'))
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': f'{jurisdiction_id.title()}-eFile-Client/1.0',
            }
            
            if api_key:
                headers['X-API-Key'] = api_key
                
            # Add Tyler token if available (following auth_views.py pattern)
            if tyler_token:
                headers[f'TYLER-TOKEN-{jurisdiction_id.upper()}'] = tyler_token
            else:
                print(f"Warning: No Tyler token found for jurisdiction '{jurisdiction_id}' in filing submission")
            
            print('Submitting to Suffolk LIT Lab API at:', api_url)
            print('With headers:', headers)
            print('API Key present:', bool(api_key))
            print('Tyler Token present:', bool(tyler_token))
            print('Request payload:', json.dumps(efile_data, indent=2))
            
            response = requests.post(
                api_url,
                json=efile_data,
                headers=headers,
            )
            
            print(f'Response status code: {response.status_code}')
            print(f'Response headers: {dict(response.headers)}')
            print(f'Response content: {response.text}')
            
            if response.status_code == 200 or response.status_code == 201:
                response_data = response.json()
                
                # Clear session data after successful submission
                if 'case_data' in request.session:
                    del request.session['case_data']
                if 'upload_data' in request.session:
                    del request.session['upload_data']
                request.session.modified = True
                
                return JsonResponse({
                    'success': True,
                    'message': 'Filing submitted successfully',
                    'redirect_url': '/filing-confirmation/',
                    'api_response': response_data
                })
            else:
                # Handle API error responses
                print(f'API Error - Status: {response.status_code}')
                print(f'API Error - Response: {response.text}')
                
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', f'API returned status {response.status_code}')
                    
                    # For 400 errors, include more details
                    if response.status_code == 400:
                        validation_errors = error_data.get('validation_errors', error_data.get('errors', []))
                        if validation_errors:
                            error_message += f' - Validation errors: {validation_errors}'
                            
                except json.JSONDecodeError:
                    error_message = f'API returned status {response.status_code} - Response: {response.text}'
                except Exception as parse_error:
                    error_message = f'API returned status {response.status_code} - Could not parse response: {str(parse_error)}'
                
                return JsonResponse({
                    'success': False,
                    'error': f'Filing submission failed: {error_message}',
                    'api_status_code': response.status_code,
                    'api_response': response.text[:500] if response.text else 'No response body'
                }, status=response.status_code)
                
        except requests.RequestException as e:
            return JsonResponse({
                'success': False,
                'error': f'Network error during filing submission: {str(e)}'
            }, status=500)
        
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


@csrf_exempt
@require_http_methods(["POST"])
def api_save_case_data(request):
    """
    API endpoint to save case data to session
    """
    try:
        data = json.loads(request.body)

        # Handle two different data structures:
        # 1. From form-validation.js: { data: { form_fields... } }
        # 2. From case_details.html: { existing_case: 'yes', case_tracking_id: '...', ... }
        
        if 'data' in data:
            # Structure from form-validation.js (expert form)
            form_data = data.get('data', {})
            existing_case = form_data.get('existing_case')
        else:
            # Structure from case_details.html (direct fields)
            form_data = data
            existing_case = data.get('existing_case')
        
        # Save existing_case to session if provided
        if existing_case:
            request.session['existing_case'] = existing_case
        
        # Always save all form data to case_data for upload view compatibility
        case_data = request.session.get('case_data', {})
        case_data.update(form_data)
        
        # Ensure existing_case status is available in case_data
        if existing_case:
            case_data['existing_case'] = existing_case
        
        # Map case details fields to standard names for eFiling
        if 'case_docket_id' in form_data:
            case_data['docket_number'] = form_data['case_docket_id']
        if 'case_tracking_id' in form_data:
            case_data['previous_case_id'] = form_data['case_tracking_id']
        
        # Determine party type for existing cases - typically defendant/respondent when responding to existing case
        if existing_case == 'yes':
            # For existing cases, we need to determine the appropriate party type
            # This depends on the case type and filing type
            party_type = determine_party_type_for_existing_case(form_data)
            if not case_data.get('party_type'):
                case_data['party_type'] = party_type
            if not case_data.get('petitioner_party_type'):
                case_data['petitioner_party_type'] = party_type
            
        request.session['case_data'] = case_data
        request.session.modified = True
        
        return JsonResponse({
            "success": True, 
            "data": {"existing_case": existing_case, "saved_fields": list(form_data.keys())}
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False, 
            "error": "Invalid JSON data"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "success": False, 
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def fetch_and_save_party_type(request):
    """
    Fetch party type code from Suffolk LIT Lab API and save to session
    """
    try:
        data = json.loads(request.body)
        court_code = data.get('court')
        case_type_code = data.get('case_type')
        existing_case = data.get('existing_case')
        jurisdiction = data.get('jurisdiction', 'illinois')
        
        print(f"Fetching party type with data: {data}")
        
        if not court_code or not case_type_code:
            return JsonResponse({
                "success": False,
                "error": "Court and case_type are required"
            }, status=400)
        
        # Determine target party type based on existing case status
        if existing_case == 'yes':
            print("Determining party type for existing case")
            party_type_code = determine_party_type_for_existing_case({
                'court': court_code,
                'case_type': case_type_code,
                'filing_type': data.get('filing_type', ''),
                'existing_case': existing_case
            })
        else:
            print("Determining party type for new case")
            # For new cases, determine appropriate party type
            case_type = case_type_code.lower()
            print(f"Case type (lowercase): {case_type}")
            
            if 'name change' in case_type or 'family' in case_type or 'probate' in case_type:
                print("Looking for petitioner party type")
                party_type_code = get_party_type_code_from_api(court_code, case_type_code, target_party_name='petitioner')
            elif 'civil' in case_type:
                print("Looking for plaintiff party type")
                party_type_code = get_party_type_code_from_api(court_code, case_type_code, target_party_name='plaintiff')
            else:
                print("Default: Looking for petitioner party type")
                party_type_code = get_party_type_code_from_api(court_code, case_type_code, target_party_name='petitioner')
            
            # If API call failed, return error instead of using fallback codes
            if not party_type_code:
                print("API call failed, no party type could be determined from Suffolk API")
                return JsonResponse({
                    "success": False,
                    "error": f"Unable to determine party type from Suffolk API for court '{court_code}' and case type '{case_type_code}'"
                }, status=400)
        
        print(f"Final party type code: {party_type_code}")
        
        # Save to session
        case_data = request.session.get('case_data', {})
        case_data['determined_party_type'] = party_type_code
        case_data['party_type'] = party_type_code
        case_data['petitioner_party_type'] = party_type_code
        request.session['case_data'] = case_data
        request.session.modified = True
        
        print(f"Saved party type to session: {party_type_code}")
        
        return JsonResponse({
            "success": True,
            "party_type": party_type_code
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON data"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_party_type_to_session(request):
    """
    Save party type code to session after it's been fetched from Suffolk API on frontend
    """
    try:
        data = json.loads(request.body)
        party_type = data.get('party_type')
        party_types_available = data.get('party_types_available', [])
        
        if not party_type:
            return JsonResponse({
                "success": False,
                "error": "Party type is required"
            }, status=400)
        
        # Save to session
        case_data = request.session.get('case_data', {})
        case_data['determined_party_type'] = party_type
        case_data['party_type'] = party_type
        case_data['petitioner_party_type'] = party_type
        case_data['available_party_types'] = party_types_available
        request.session['case_data'] = case_data
        request.session.modified = True
        
        print(f"Saved party type to session: {party_type}")
        
        return JsonResponse({
            "success": True,
            "party_type": party_type
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON data"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_party_types_from_suffolk_api(request):
    """
    Fetch party types directly from Suffolk API and save to session (GET request)
    """
    try:
        jurisdiction = request.GET.get('jurisdiction', 'illinois')
        court = request.GET.get('court')
        case_type = request.GET.get('case_type')
        existing_case = request.GET.get('existing_case', 'no')
        
        if not court or not case_type:
            return JsonResponse({
                "success": False,
                "error": "Court and case_type parameters are required"
            }, status=400)
        
        # Construct Suffolk API URL
        suffolk_api_url = f"https://efile-test.suffolklitlab.org/jurisdictions/{jurisdiction}/codes/courts/{court}/case_types/{case_type}/party_types"
        
        print(f"Fetching party types from Suffolk API: {suffolk_api_url}")
        print(f"Existing case: {existing_case}")
        
        # Make request to Suffolk API
        response = requests.get(suffolk_api_url, timeout=10)
        
        if response.status_code == 200:
            party_types = response.json()
            print(f"Suffolk API returned {len(party_types)} party types:")
            for pt in party_types:
                print(f"  - {pt.get('name', 'No name')} ({pt.get('code', 'No code')})")
            
            if party_types and len(party_types) > 0:
                # Determine appropriate party type based on case status
                selected_party_type = None
                
                if existing_case == 'yes':
                    # For existing cases, look for defendant party type
                    print("Looking for defendant party type for existing case")
                    for party_type in party_types:
                        if isinstance(party_type, dict) and "name" in party_type and "code" in party_type:
                            party_name_lower = party_type["name"].lower()
                            if ('defendant' in party_name_lower or 
                                'respondent' in party_name_lower or
                                'def' in party_name_lower):
                                selected_party_type = party_type["code"]
                                print(f"Found defendant/respondent party type: {party_type['name']} ({selected_party_type})")
                                break
                else:
                    # For new cases, look for petitioner or plaintiff party type
                    print("Looking for petitioner/plaintiff party type for new case")
                    case_type_lower = case_type.lower()
                    
                    target_names = []
                    if 'name change' in case_type_lower or 'family' in case_type_lower or 'probate' in case_type_lower:
                        target_names = ['petitioner', 'pet']
                    elif 'civil' in case_type_lower:
                        target_names = ['plaintiff', 'pl']
                    else:
                        target_names = ['petitioner', 'pet', 'plaintiff', 'pl']
                    
                    for target_name in target_names:
                        for party_type in party_types:
                            if isinstance(party_type, dict) and "name" in party_type and "code" in party_type:
                                party_name_lower = party_type["name"].lower()
                                if target_name in party_name_lower:
                                    selected_party_type = party_type["code"]
                                    print(f"Found {target_name} party type: {party_type['name']} ({selected_party_type})")
                                    break
                        if selected_party_type:
                            break
                
                # If no specific match found, use the first available party type
                if not selected_party_type:
                    selected_party_type = party_types[0].get('code')
                    print(f"No specific match found, using first party type: {party_types[0].get('name', 'Unknown')} ({selected_party_type})")
                
                # Save to session
                case_data = request.session.get('case_data', {})
                case_data['determined_party_type'] = selected_party_type
                case_data['party_type'] = selected_party_type
                case_data['petitioner_party_type'] = selected_party_type
                case_data['available_party_types'] = party_types
                case_data['existing_case'] = existing_case  # Save existing case status
                request.session['case_data'] = case_data
                request.session.modified = True
                
                print(f"Saved party type to session: {selected_party_type}")
                
                return JsonResponse({
                    "success": True,
                    "party_types": party_types,
                    "selected_party_type": selected_party_type
                })
            else:
                return JsonResponse({
                    "success": False,
                    "error": "No party types returned from Suffolk API"
                }, status=400)
        else:
            print(f"Suffolk API request failed with status: {response.status_code}")
            print(f"Response: {response.text}")
            return JsonResponse({
                "success": False,
                "error": f"Suffolk API returned status {response.status_code}"
            }, status=response.status_code)
                
    except requests.RequestException as e:
        print(f"Network error calling Suffolk API: {e}")
        return JsonResponse({
            "success": False,
            "error": f"Network error: {str(e)}"
        }, status=500)
    except Exception as e:
        print(f"Unexpected error: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_get_case_data(request):
    """
    API endpoint to retrieve saved case data from session
    """
    try:
        existing_case = request.session.get('existing_case')
        
        data = {}
        if existing_case:
            data['existing_case'] = existing_case
        
        return JsonResponse({
            "success": True, 
            "data": data
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False, 
            "error": str(e)
        }, status=500)
