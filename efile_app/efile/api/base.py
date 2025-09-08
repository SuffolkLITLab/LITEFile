"""
Base API views and utilities for Illinois eFile system
"""

from django.http import JsonResponse


class APIResponseMixin:
    """Mixin for consistent API responses"""

    @staticmethod
    def success_response(data, message=None):
        """Return a successful API response"""
        response = {"success": True, "data": data}
        if message:
            response["message"] = message
        return JsonResponse(response)

    @staticmethod
    def error_response(error_message, status_code=400):
        """Return an error API response"""
        return JsonResponse({"success": False, "error": error_message}, status=status_code)


def get_auth_tokens(request):
    """Helper function to get auth tokens from session"""
    return request.session.get("auth_tokens", None)


def validate_request(request, required_params=None):
    """Validate API request and return any missing parameters"""
    if required_params is None:
        required_params = []

    missing_params = []
    for param in required_params:
        if param not in request.GET and param not in request.POST:
            missing_params.append(param)

    return missing_params
