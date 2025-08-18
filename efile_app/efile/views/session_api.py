from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json


@csrf_exempt
@require_http_methods(["POST"])
def save_form_data_to_session(request):
    """Simple endpoint to save form data from localStorage to Django session."""
    try:
        data = json.loads(request.body)
        form_data = data.get('data', {})
        
        # Extract case data from form submission
        case_data = {
            'court': form_data.get('court', ''),
            'case_category': form_data.get('case_category', ''),
            'case_type': form_data.get('case_type', ''),
            'filing_type': form_data.get('filing_type', ''),
            'document_type': form_data.get('document_type', ''),
            'petitioner_first_name': form_data.get('petitioner_first_name', ''),
            'petitioner_last_name': form_data.get('petitioner_last_name', ''),
            'petitioner_address': form_data.get('petitioner_address', ''),
            'new_first_name': form_data.get('new_first_name', ''),
            'new_last_name': form_data.get('new_last_name', ''),
            'optional_services': form_data.get('optional_services', []),
            # Include friendly names for display
            'court_name': form_data.get('court_name', ''),
            'case_category_name': form_data.get('case_category_name', ''),
            'case_type_name': form_data.get('case_type_name', ''),
            'filing_type_name': form_data.get('filing_type_name', ''),
            'document_type_name': form_data.get('document_type_name', ''),
        }
        
        # Save to session
        request.session['case_data'] = case_data
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'message': 'Case data saved to session'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
