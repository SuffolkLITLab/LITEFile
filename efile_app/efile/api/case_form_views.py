"""
API views for dynamic case form configuration
Provides case-specific form structure based on document type selection
Uses case-type-forms.yaml for dynamic form generation
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .base import APIResponseMixin
import yaml
import os


class CaseFormAPIViews(APIResponseMixin):
    """API views for dynamic case form configuration"""
    
    @staticmethod
    def _load_case_type_forms():
        """Load case type forms configuration from YAML"""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'static', 'config', 'case-type-forms.yaml'
            )
            
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            print(f"Error loading case-type-forms.yaml: {e}")
            return None
    
    @staticmethod
    def _find_case_type_by_keywords(case_type_name):
        """Find case type configuration by matching keywords"""
        forms_config = CaseFormAPIViews._load_case_type_forms()
        if not forms_config or 'case_types' not in forms_config:
            return None
            
        case_type_name_lower = case_type_name.lower()
        
        # Try exact match first
        if case_type_name_lower in forms_config['case_types']:
            return forms_config['case_types'][case_type_name_lower]
            
        # Try keyword matching
        for case_type_key, case_type_config in forms_config['case_types'].items():
            if 'keywords' in case_type_config:
                for keyword in case_type_config['keywords']:
                    if keyword.lower() in case_type_name_lower:
                        return case_type_config
        
        return None
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_case_form_config(request):
        """
        Get case form configuration based on selected document type
        Returns required parties configuration for dynamic form rendering
        """
        try:
            # Get parameters from request
            court_code = request.GET.get('court')
            category_id = request.GET.get('category')
            case_type_id = request.GET.get('case_type')
            filing_type_id = request.GET.get('filing_type')
            document_type_id = request.GET.get('document_type')
            
            if not all([court_code, document_type_id]):
                return CaseFormAPIViews.error_response(
                    "Missing required parameters: court, document_type"
                )
            
            # Try to find case type configuration using case_type_id as the name
            case_config = None
            if case_type_id:
                case_config = CaseFormAPIViews._find_case_type_by_keywords(case_type_id)
            
            # If no specific configuration found, return minimal structure
            if not case_config:
                return CaseFormAPIViews.success_response({
                    'case_info': {
                        'category': category_id,
                        'case_type': case_type_id,
                        'filing_type': filing_type_id,
                        'document_type': document_type_id
                    },
                    'sections': {},
                    'show_parties_section': False,
                    'show_services_section': False
                })
            
            # Structure the response based on case-type-forms.yaml format
            form_config = {
                'case_info': {
                    'category': category_id,
                    'case_type': case_type_id,
                    'filing_type': filing_type_id,
                    'document_type': document_type_id
                },
                'sections': case_config.get('sections', {}),
                'show_parties_section': len(case_config.get('sections', {})) > 0,
                'show_services_section': False  # Services are handled separately via API
            }
            
            return CaseFormAPIViews.success_response(form_config)
            
        except Exception as e:
            return CaseFormAPIViews.error_response(f"Error retrieving case form configuration: {str(e)}")


# Export the view function for URL mapping
get_case_form_config = CaseFormAPIViews.get_case_form_config
