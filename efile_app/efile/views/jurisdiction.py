"""
Jurisdiction management views
"""
from django.shortcuts import redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json

@require_POST
def switch_jurisdiction(request):
    """Switch user's jurisdiction preference"""
    try:
        data = json.loads(request.body)
        jurisdiction = data.get('jurisdiction')
        
        # Validate jurisdiction
        valid_jurisdictions = ['illinois', 'massachusetts']
        if jurisdiction not in valid_jurisdictions:
            return JsonResponse({'error': 'Invalid jurisdiction'}, status=400)
        
        # Update session
        request.session['jurisdiction'] = jurisdiction
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'jurisdiction': jurisdiction,
            'message': f'Switched to {jurisdiction.title()}'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_current_jurisdiction(request):
    """Get current jurisdiction info"""
    current_jurisdiction = request.session.get('jurisdiction', 'illinois')
    
    jurisdiction_configs = {
        'illinois': {
            'name': 'Illinois eFile',
            'code': 'illinois',
            'display_name': 'Illinois'
        },
        'massachusetts': {
            'name': 'Massachusetts eFile', 
            'code': 'massachusetts',
            'display_name': 'Massachusetts'
        }
    }
    
    return JsonResponse({
        'current_jurisdiction': current_jurisdiction,
        'config': jurisdiction_configs.get(current_jurisdiction)
    })
