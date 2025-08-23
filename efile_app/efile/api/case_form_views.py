"""
API views for dynamic case form configuration
Provides case-specific form stru        case_type_name_lower = case_type_name.lower()
        found_config = None
        
        for case_types in case_types_sources:based on document type selection
Uses jurisdiction-aware configuration system with base-case-types.yaml and state overrides
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .base import APIResponseMixin
import yaml
import os
from functools import lru_cache


class CaseFormAPIViews(APIResponseMixin):
    """API views for dynamic case form configuration"""
    
    @staticmethod
    @lru_cache(maxsize=32)
    def _load_base_configuration():
        """Load base case type configuration from base-case-types.yaml"""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'static', 'config', 'base-case-types.yaml'
            )
            
            with open(config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file) or {}
        except Exception as e:
            print(f"Error loading base-case-types.yaml: {e}")
            return {}
    
    @staticmethod
    @lru_cache(maxsize=32)
    def _load_jurisdiction_configuration(jurisdiction='illinois'):
        """Load jurisdiction-specific configuration and merge with base"""
        try:
            # Load base configuration first
            base_config = CaseFormAPIViews._load_base_configuration()
            
            # Load jurisdiction-specific configuration
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'static', 'config', 'states', f'{jurisdiction}.yaml'
            )
            
            jurisdiction_config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file:
                    jurisdiction_config = yaml.safe_load(file) or {}
            
            # Merge configurations - jurisdiction overrides base
            return CaseFormAPIViews._deep_merge_configs(base_config, jurisdiction_config)
            
        except Exception as e:
            print(f"Error loading jurisdiction configuration for {jurisdiction}: {e}")
            return CaseFormAPIViews._load_base_configuration()
    
    @staticmethod
    def _deep_merge_configs(base, overlay):
        """Deep merge two configuration dictionaries"""
        merged = base.copy()
        
        for key, value in overlay.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = CaseFormAPIViews._deep_merge_configs(merged[key], value)
            else:
                merged[key] = value
                
        return merged
    
    @staticmethod
    def _find_case_type_config(case_type_name, jurisdiction='illinois'):
        """Find case type configuration by matching keywords in merged config"""
        config = CaseFormAPIViews._load_jurisdiction_configuration(jurisdiction)
        
        # Check both case_types and base_case_types sections
        case_types_sources = [
            config.get('case_types', {}),
            config.get('base_case_types', {})
        ]
        
        case_type_name_lower = case_type_name.lower()
        found_config = None
        
        print(f"� Looking for case type: '{case_type_name}' (lower: '{case_type_name_lower}')")
        
        for case_types in case_types_sources:
            # Try exact match first
            if case_type_name_lower in case_types:
                found_config = case_types[case_type_name_lower]
                break
                
            # Try keyword matching
            for case_type_key, case_type_config in case_types.items():
                if 'keywords' in case_type_config:
                    for keyword in case_type_config['keywords']:
                        # Check both substring matching and exact matching
                        keyword_lower = keyword.lower()
                        if (keyword_lower in case_type_name_lower or 
                            case_type_name_lower in keyword_lower or 
                            keyword_lower == case_type_name_lower):
                            found_config = case_type_config
                            break
                if found_config:
                    break
            if found_config:
                break
        
        if not found_config:
            return None
            
        # Resolve inheritance if extends is present
        if 'extends' in found_config:
            extends_ref = found_config['extends']
            base_config = None
            
            # Parse the extends reference (e.g., "base_case_types.name_change")
            if '.' in extends_ref:
                section, key = extends_ref.split('.', 1)
                if section in config and key in config[section]:
                    base_config = config[section][key]
            
            if base_config:
                # Deep merge base config with the current config
                merged_config = CaseFormAPIViews._deep_merge_configs(base_config.copy(), found_config)
                return merged_config
        
        return found_config
    
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
            jurisdiction = request.GET.get('jurisdiction', 'illinois')
            
            # Get jurisdiction from session if not provided in query params
            if not jurisdiction:
                jurisdiction = request.session.get('jurisdiction', 'illinois')
            
            if not all([court_code, document_type_id]):
                return CaseFormAPIViews.error_response(
                    "Missing required parameters: court, document_type"
                )
            
            # Try to find case type configuration using jurisdiction-aware lookup
            case_config = None
            if case_type_id:
                case_config = CaseFormAPIViews._find_case_type_config(case_type_id, jurisdiction)
            
            # If no specific configuration found, return minimal structure
            if not case_config:
                return CaseFormAPIViews.success_response({
                    'case_info': {
                        'jurisdiction': jurisdiction,
                        'category': category_id,
                        'case_type': case_type_id,
                        'filing_type': filing_type_id,
                        'document_type': document_type_id
                    },
                    'sections': {},
                    'show_parties_section': False,
                    'show_services_section': False
                })
            
            # Apply court-specific customizations if they exist
            sections = case_config.get('sections', {})
            if court_code:
                sections = CaseFormAPIViews._apply_court_specific_config(
                    sections, court_code, case_type_id, jurisdiction
                )
            
            # Structure the response based on the new configuration format
            form_config = {
                'case_info': {
                    'jurisdiction': jurisdiction,
                    'category': category_id,
                    'case_type': case_type_id,
                    'filing_type': filing_type_id,
                    'document_type': document_type_id,
                    'description': case_config.get('description', '')
                },
                'sections': sections,
                'show_parties_section': len(sections) > 0,
                'show_services_section': False,  # Services are handled separately via API
                'validation_rules': case_config.get('validation_rules', [])
            }
            
            return CaseFormAPIViews.success_response(form_config)
            
        except Exception as e:
            return CaseFormAPIViews.error_response(f"Error retrieving case form configuration: {str(e)}")
    
    @staticmethod
    def _apply_court_specific_config(sections, court_code, case_type_id, jurisdiction):
        """Apply court-specific configurations and conditional requirements"""
        try:
            config = CaseFormAPIViews._load_jurisdiction_configuration(jurisdiction)
            court_requirements = config.get('court_specific_requirements', {}).get(court_code, {})
            
            if not court_requirements:
                return sections
            
            case_specific = court_requirements.get('case_types', {}).get(case_type_id, {})
            if not case_specific:
                return sections
            
            # Apply field modifications first
            field_modifications = case_specific.get('field_modifications', [])
            for modification in field_modifications:
                field_group_name = modification.get('field_group')
                modifications = modification.get('modifications', {})
                
                # Apply modifications to the matching field group
                if 'parties' in sections and 'fields' in sections['parties']:
                    # Use a copy of the list to avoid modification during iteration
                    fields_list = sections['parties']['fields'][:]
                    for field_group in fields_list:
                        if field_group.get('section_title') == field_group_name:
                            # Apply modifications to this field group
                            for key, value in modifications.items():
                                if key == 'hidden' and value:
                                    # Remove this field group entirely if hidden
                                    if field_group in sections['parties']['fields']:
                                        sections['parties']['fields'].remove(field_group)
                                    break
                                elif key == 'required':
                                    field_group['required'] = value
                                elif key == 'conditional_requirements':
                                    field_group['conditional_requirements'] = value
                            break
            
            # Apply additional fields
            additional_fields = case_specific.get('additional_fields', [])
            if additional_fields and 'parties' in sections and 'fields' in sections['parties']:
                # Add additional fields to the first section of parties
                if sections['parties']['fields']:
                    first_section = sections['parties']['fields'][0]
                    if 'fields' in first_section:
                        # Check for existing fields to prevent duplicates
                        existing_field_names = {field.get('name') for field in first_section['fields']}
                        
                        # Only add fields that don't already exist
                        new_fields = []
                        for field in additional_fields:
                            field_name = field.get('name')
                            if field_name and field_name not in existing_field_names:
                                new_fields.append(field)
                        
                        if new_fields:
                            first_section['fields'].extend(new_fields)
            
            return sections
            
        except Exception as e:
            print(f"Error applying court-specific config: {e}")
            return sections
