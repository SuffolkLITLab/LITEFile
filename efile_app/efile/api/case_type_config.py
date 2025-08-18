import yaml
import json
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.conf import settings
import os

@cache_page(60 * 15)  # Cache for 15 minutes
def get_case_type_config(request):
    """
    Serves the case type configuration from YAML file as JSON
    """
    try:
        config_path = os.path.join(settings.BASE_DIR, 'efile', 'static', 'config', 'case-type-forms.yaml')
        
        with open(config_path, 'r', encoding='utf-8') as file:
            config_data = yaml.safe_load(file)
        
        return JsonResponse({
            'success': True,
            'config': config_data
        })
        
    except FileNotFoundError:
        return JsonResponse({
            'success': False,
            'error': 'Configuration file not found'
        }, status=404)
        
    except yaml.YAMLError as e:
        return JsonResponse({
            'success': False,
            'error': f'YAML parsing error: {str(e)}'
        }, status=500)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)
