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
