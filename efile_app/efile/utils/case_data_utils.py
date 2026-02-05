"""
Utility functions for handling case data throughout the application
"""


def get_case_data(request):
    """
    Get case data from session with safe defaults
    """
    return request.session.get("case_data", {})


def update_case_data(request, updates):
    """
    Update specific fields in the case data
    """
    case_data = get_case_data(request)
    case_data.update(updates)
    request.session["case_data"] = case_data
    request.session.modified = True
    return case_data


def clear_case_data(request):
    """
    Clear all case data from session
    """
    if "case_data" in request.session:
        del request.session["case_data"]
        request.session.modified = True


def get_upload_data(request):
    return request.session.get("upload_data", {})


def update_upload_data(request, updates):
    upload_data = get_upload_data(request)
    upload_data.update(updates)
    request.session["upload_data"] = upload_data
    request.session.modified = True
    return upload_data


def clear_upload_data(request):
    if "upload_data" in request.session:
        del request.session["upload_data"]
        request.session.modified = True


def get_petitioner_info(request):
    """
    Get petitioner information specifically
    """
    case_data = get_case_data(request)
    full_name = f"{case_data.get('petitioner_first_name', '')} {case_data.get('petitioner_last_name', '')}".strip()
    return {
        "first_name": case_data.get("petitioner_first_name", ""),
        "last_name": case_data.get("petitioner_last_name", ""),
        "address": case_data.get("petitioner_address", ""),
        "full_name": full_name,
    }


def get_name_sought_info(request):
    """
    Get name sought information specifically
    """
    case_data = get_case_data(request)
    return {
        "first_name": case_data.get("new_first_name", ""),
        "last_name": case_data.get("new_last_name", ""),
        "full_name": f"{case_data.get('new_first_name', '')} {case_data.get('new_last_name', '')}".strip(),
    }


def get_case_classification(request):
    """
    Get case classification information
    """
    case_data = get_case_data(request)
    return {
        "court": case_data.get("court", ""),
        "case_category": case_data.get("case_category", ""),
        "case_type": case_data.get("case_type", ""),
        "filing_type": case_data.get("filing_type", ""),
        "document_type": case_data.get("document_type", ""),
        "is_name_change": "name change" in case_data.get("case_type", "").lower(),
    }


def get_selected_services(request):
    """
    Get list of selected optional services
    """
    case_data = get_case_data(request)
    return case_data.get("optional_services", [])
