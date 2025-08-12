"""
API views for filing operations and document management
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import requests
import json
from .base import APIResponseMixin, get_auth_tokens, validate_request


class FilingAPIViews(APIResponseMixin):
    """API views for filing operations"""
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_filings(request):
        """Get user's filings"""
        try:
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)
            
            # API call to get user's filings
            response = requests.get(
                'https://suffolkefile.com/api/filings',
                headers={'Authorization': f'Bearer {auth_tokens["access_token"]}'}
            )
            
            if response.status_code == 200:
                data = response.json()
                return FilingAPIViews.success_response(data.get('filings', []))
            else:
                return FilingAPIViews.error_response("Failed to fetch filings")
                
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["POST"])
    @csrf_exempt
    def create_filing(request):
        """Create a new filing"""
        try:
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)
            
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['case_category', 'case_type', 'filing_type', 'county']
            missing_fields = [field for field in required_fields if not data.get(field)]
            
            if missing_fields:
                return FilingAPIViews.error_response(
                    f"Missing required fields: {', '.join(missing_fields)}"
                )
            
            # API call to create filing
            response = requests.post(
                'https://suffolkefile.com/api/filings',
                json=data,
                headers={'Authorization': f'Bearer {auth_tokens["access_token"]}'}
            )
            
            if response.status_code == 201:
                filing_data = response.json()
                return FilingAPIViews.success_response(filing_data, "Filing created successfully")
            else:
                return FilingAPIViews.error_response("Failed to create filing")
                
        except json.JSONDecodeError:
            return FilingAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_filing_detail(request, filing_id):
        """Get details for a specific filing"""
        try:
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)
            
            # API call to get filing details
            response = requests.get(
                f'https://suffolkefile.com/api/filings/{filing_id}',
                headers={'Authorization': f'Bearer {auth_tokens["access_token"]}'}
            )
            
            if response.status_code == 200:
                filing_data = response.json()
                return FilingAPIViews.success_response(filing_data)
            elif response.status_code == 404:
                return FilingAPIViews.error_response("Filing not found", 404)
            else:
                return FilingAPIViews.error_response("Failed to fetch filing details")
                
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["PUT"])
    @csrf_exempt
    def update_filing(request, filing_id):
        """Update an existing filing"""
        try:
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)
            
            data = json.loads(request.body)
            
            # API call to update filing
            response = requests.put(
                f'https://suffolkefile.com/api/filings/{filing_id}',
                json=data,
                headers={'Authorization': f'Bearer {auth_tokens["access_token"]}'}
            )
            
            if response.status_code == 200:
                filing_data = response.json()
                return FilingAPIViews.success_response(filing_data, "Filing updated successfully")
            elif response.status_code == 404:
                return FilingAPIViews.error_response("Filing not found", 404)
            else:
                return FilingAPIViews.error_response("Failed to update filing")
                
        except json.JSONDecodeError:
            return FilingAPIViews.error_response("Invalid JSON data")
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["DELETE"])
    @csrf_exempt
    def delete_filing(request, filing_id):
        """Delete a filing"""
        try:
            auth_tokens = get_auth_tokens(request)
            if not auth_tokens:
                return FilingAPIViews.error_response("Not authenticated", 401)
            
            # API call to delete filing
            response = requests.delete(
                f'https://suffolkefile.com/api/filings/{filing_id}',
                headers={'Authorization': f'Bearer {auth_tokens["access_token"]}'}
            )
            
            if response.status_code == 204:
                return FilingAPIViews.success_response({}, "Filing deleted successfully")
            elif response.status_code == 404:
                return FilingAPIViews.error_response("Filing not found", 404)
            else:
                return FilingAPIViews.error_response("Failed to delete filing")
                
        except Exception as e:
            return FilingAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
get_filings = FilingAPIViews.get_filings
create_filing = FilingAPIViews.create_filing
get_filing_detail = FilingAPIViews.get_filing_detail
update_filing = FilingAPIViews.update_filing
delete_filing = FilingAPIViews.delete_filing
