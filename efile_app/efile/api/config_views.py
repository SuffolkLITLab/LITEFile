"""
API views for form configuration based on YAML settings
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .base import APIResponseMixin, get_auth_tokens, validate_request
from ..utils.case_type_config import case_type_config


class ConfigAPIViews(APIResponseMixin):
    """API views for form configuration"""
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_form_config(request):
        """Get complete form configuration for a specific filing type"""
        try:
            auth_tokens = get_auth_tokens(request)
            # Note: Auth check removed for mock data functionality
            
            # Get required parameters
            category_id = request.GET.get('category')
            case_type_id = request.GET.get('case_type')
            filing_type_id = request.GET.get('filing_type')
            
            if not all([category_id, case_type_id, filing_type_id]):
                return ConfigAPIViews.error_response(
                    "Missing required parameters: category, case_type, filing_type"
                )
            
            # Use case_type_id to get configuration from YAML file
            config = {
                'required_parties': case_type_config.get_required_parties(case_type_id),
                'optional_services': case_type_config.get_optional_services(case_type_id),
                'is_name_change': case_type_config.is_name_change_case(case_type_id),
                'case_type_name': case_type_config.get_case_type_config(case_type_id).get('name', 'Unknown Case Type')
            }
            
            return ConfigAPIViews.success_response(config)
                
        except Exception as e:
            return ConfigAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
get_form_config = ConfigAPIViews.get_form_config
