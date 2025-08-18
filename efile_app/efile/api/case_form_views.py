"""
API views for dynamic case form configuration
Provides case-specific form structure based on document type selection
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .base import APIResponseMixin
from ..utils.case_config import case_types_config


class CaseFormAPIViews(APIResponseMixin):
    """API views for dynamic case form configuration"""
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_case_form_config(request):
        """
        Get case form configuration based on selected document type
        Returns required parties and optional services for the specific case type
        """
        try:
            # Get parameters from request
            court_code = request.GET.get('court')
            category_id = request.GET.get('category')
            case_type_id = request.GET.get('case_type')
            filing_type_id = request.GET.get('filing_type')
            document_type_id = request.GET.get('document_type')
            
            if not all([court_code, category_id, case_type_id, filing_type_id, document_type_id]):
                return CaseFormAPIViews.error_response(
                    "Missing required parameters: court, category, case_type, filing_type, document_type"
                )
            
            # Get case configuration from YAML
            case_config = case_types_config.get_case_form_config(
                category_id, case_type_id, filing_type_id
            )
            
            if not case_config:
                return CaseFormAPIViews.error_response(
                    f"No form configuration found for the specified case type"
                )
            
            # Structure the response
            form_config = {
                'case_info': {
                    'category': category_id,
                    'case_type': case_type_id,
                    'filing_type': filing_type_id,
                    'document_type': document_type_id
                },
                'required_parties': case_config.get('required_parties', []),
                'optional_services': case_config.get('optional_services', []),
                'global_optional_services': case_types_config.get_global_optional_services(),
                'show_parties_section': len(case_config.get('required_parties', [])) > 0,
                'show_services_section': (
                    len(case_config.get('optional_services', [])) > 0 or 
                    len(case_types_config.get_global_optional_services()) > 0
                )
            }
            
            return CaseFormAPIViews.success_response(form_config)
            
        except Exception as e:
            return CaseFormAPIViews.error_response(f"Error retrieving case form configuration: {str(e)}")


# Export the view function for URL mapping
get_case_form_config = CaseFormAPIViews.get_case_form_config
