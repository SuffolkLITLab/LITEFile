"""
API views for dropdown data in Illinois eFile system
Handles cascading dropdowns for case categories, types, counties, etc.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import requests
from .base import APIResponseMixin, get_auth_tokens, validate_request


class DropdownAPIViews(APIResponseMixin):
    """API views for dropdown data"""
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_case_categories(request):
        """Get available case categories"""
        try:
            auth_tokens = get_auth_tokens(request)
            # Note: Auth check removed for mock data functionality
            
            # Mock data - replace with actual API call when available
            categories = [
                {'value': 'miscellaneous', 'text': 'Miscellaneous'},
                {'value': 'civil', 'text': 'Civil'},
                {'value': 'family', 'text': 'Family'},
                {'value': 'probate', 'text': 'Probate'}
            ]
            
            return DropdownAPIViews.success_response(categories)
                
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_case_types(request):
        """Get case types based on selected category"""
        try:
            missing_params = validate_request(request, ['parent'])
            if missing_params:
                return DropdownAPIViews.error_response(
                    f"Missing required parameters: {', '.join(missing_params)}"
                )
            
            auth_tokens = get_auth_tokens(request)
            # Note: Auth check removed for mock data functionality
            
            parent_category = request.GET.get('parent')
            
            # Mock data based on category - replace with actual API call
            type_mapping = {
                'miscellaneous': [
                    {'value': 'name_change', 'text': 'Name Change'},
                    {'value': 'other_misc', 'text': 'Other Miscellaneous'}
                ],
                'civil': [
                    {'value': 'small_claims', 'text': 'Small Claims'},
                    {'value': 'contract_dispute', 'text': 'Contract Dispute'}
                ],
                'family': [
                    {'value': 'divorce', 'text': 'Divorce'},
                    {'value': 'custody', 'text': 'Child Custody'}
                ],
                'probate': [
                    {'value': 'will_probate', 'text': 'Will Probate'},
                    {'value': 'estate_admin', 'text': 'Estate Administration'}
                ]
            }
            
            case_types = type_mapping.get(parent_category, [])
            return DropdownAPIViews.success_response(case_types)
                
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_filing_types(request):
        """Get filing types based on selected case type"""
        try:
            missing_params = validate_request(request, ['parent'])
            if missing_params:
                return DropdownAPIViews.error_response(
                    f"Missing required parameters: {', '.join(missing_params)}"
                )
            
            auth_tokens = get_auth_tokens(request)
            # Note: Auth check removed for mock data functionality
            
            parent_type = request.GET.get('parent')
            
            # Mock data based on case type - replace with actual API call
            filing_mapping = {
                'name_change': [
                    {'value': 'petition_name_change', 'text': 'Petition for Name Change'},
                    {'value': 'supplemental_petition', 'text': 'Supplemental Petition'}
                ],
                'small_claims': [
                    {'value': 'complaint', 'text': 'Complaint'},
                    {'value': 'counterclaim', 'text': 'Counterclaim'}
                ],
                'divorce': [
                    {'value': 'petition_divorce', 'text': 'Petition for Divorce'},
                    {'value': 'response_divorce', 'text': 'Response to Divorce'}
                ]
            }
            
            filing_types = filing_mapping.get(parent_type, [])
            return DropdownAPIViews.success_response(filing_types)
                
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_counties(request):
        """Get available counties"""
        try:
            auth_tokens = get_auth_tokens(request)
            # Note: Auth check removed for mock data functionality
            
            # Illinois counties - replace with actual API call if needed
            counties = [
                {'value': 'cook', 'text': 'Cook County'},
                {'value': 'dupage', 'text': 'DuPage County'},
                {'value': 'kane', 'text': 'Kane County'},
                {'value': 'lake', 'text': 'Lake County'},
                {'value': 'mchenry', 'text': 'McHenry County'},
                {'value': 'will', 'text': 'Will County'}
            ]
            
            return DropdownAPIViews.success_response(counties)
                
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")
    
    @staticmethod
    @require_http_methods(["GET"])
    def get_document_types(request):
        """Get document types based on selected filing type"""
        try:
            # Document types don't require parent parameter - they're fairly static
            auth_tokens = get_auth_tokens(request)
            # Note: Auth check removed for mock data functionality
            
            parent = request.GET.get('parent')  # Optional for future use
            
            # Mock data - replace with actual API call
            document_types = [
                {'value': 'non_confidential', 'text': 'Non-Confidential'},
                {'value': 'confidential', 'text': 'Confidential'},
                {'value': 'sealed', 'text': 'Sealed Document'}
            ]
            
            return DropdownAPIViews.success_response(document_types)
                
        except Exception as e:
            return DropdownAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
get_case_categories = DropdownAPIViews.get_case_categories
get_case_types = DropdownAPIViews.get_case_types
get_filing_types = DropdownAPIViews.get_filing_types
get_counties = DropdownAPIViews.get_counties
get_document_types = DropdownAPIViews.get_document_types
