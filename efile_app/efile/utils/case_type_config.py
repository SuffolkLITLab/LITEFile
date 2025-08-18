"""
Case Type Configuration Handler
Reads YAML configuration to determine form structure based on case type
"""
import yaml
import os
from typing import Dict, Any, Optional
from django.conf import settings


class CaseTypeConfig:
    """Handles loading and accessing case type configuration from YAML"""
    
    def __init__(self):
        self.config = None
        self.config_path = os.path.join(
            settings.BASE_DIR, 
            'efile', 
            'static',
            'config', 
            'case_types_config.yml'
        )
        self.load_config()
    
    def load_config(self):
        """Load the YAML configuration file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file)
                print(f"Loaded case type config from {self.config_path}")
        except FileNotFoundError:
            print(f"Warning: Case type config file not found at {self.config_path}")
            self.config = self._get_default_config()
        except yaml.YAMLError as e:
            print(f"Error parsing YAML config: {e}")
            self.config = self._get_default_config()
        except Exception as e:
            print(f"Error loading case type config: {e}")
            self.config = self._get_default_config()
    
    def _get_default_config(self):
        """Fallback configuration if YAML file can't be loaded"""
        return {
            'case_categories': {
                'miscellaneous': {
                    'name': 'Miscellaneous',
                    'case_types': {
                        'default': {
                            'name': 'General Case',
                            'filing_types': {
                                'general': {
                                    'name': 'General Filing',
                                    'required_parties': [
                                        {
                                            'id': 'petitioner',
                                            'name': 'Petitioner',
                                            'title': 'Petitioner',
                                            'required': True,
                                            'fields': [
                                                {'name': 'first_name', 'label': 'First Name', 'type': 'text', 'required': True},
                                                {'name': 'last_name', 'label': 'Last Name', 'type': 'text', 'required': True},
                                                {'name': 'address', 'label': 'Address', 'type': 'textarea', 'required': True}
                                            ]
                                        }
                                    ],
                                    'optional_services': [],
                                    'document_types': []
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def get_case_type_config(self, case_type_id: str) -> Dict[str, Any]:
        """Get configuration for a specific case type ID"""
        if not self.config or 'case_categories' not in self.config:
            return self._get_default_config()['case_categories']['miscellaneous']['case_types']['default']
        
        # Handle different case type mappings based on Suffolk API case type IDs
        case_type_mapping = {
            '1': 'name_change',
            '2': 'small_claims', 
            '3': 'contract_dispute',
            '4': 'divorce',
            '5': 'will_probate'
        }
        
        case_type_key = case_type_mapping.get(case_type_id, case_type_id)
        
        # Search through case categories for the case type
        for category_key, category in self.config.get('case_categories', {}).items():
            case_types = category.get('case_types', {})
            if case_type_key in case_types:
                case_type_config = case_types[case_type_key]
                
                # Return the first filing type for now (could be enhanced to select specific filing type)
                filing_types = case_type_config.get('filing_types', {})
                if filing_types:
                    first_filing_type = next(iter(filing_types.values()))
                    
                    # Merge with global optional services
                    optional_services = first_filing_type.get('optional_services', [])
                    global_services = self.config.get('global_optional_services', [])
                    all_optional_services = optional_services + global_services
                    
                    # Merge with default document types
                    document_types = first_filing_type.get('document_types', [])
                    default_docs = self.config.get('default_document_types', [])
                    all_document_types = document_types + default_docs
                    
                    return {
                        'case_type_name': case_type_config.get('name', ''),
                        'category': category.get('name', ''),
                        'required_parties': first_filing_type.get('required_parties', []),
                        'optional_services': all_optional_services,
                        'document_types': all_document_types,
                        'filing_type_name': first_filing_type.get('name', '')
                    }
        
        # Return default structure if not found
        return {
            'case_type_name': 'General Case',
            'category': 'Miscellaneous',
            'required_parties': [],
            'optional_services': [],
            'document_types': [],
            'filing_type_name': 'General Filing'
        }
    
    def is_name_change_case(self, case_type_id: str) -> bool:
        """Check if a case type is a name change case"""
        case_type_mapping = {
            '1': 'name_change',
        }
        case_type_key = case_type_mapping.get(case_type_id, case_type_id)
        return case_type_key == 'name_change'
    
    def get_required_parties(self, case_type_id: str) -> list:
        """Get required parties configuration for a case type"""
        config = self.get_case_type_config(case_type_id)
        return config.get('required_parties', [])
    
    def get_optional_services(self, case_type_id: str) -> list:
        """Get optional services configuration for a case type"""
        config = self.get_case_type_config(case_type_id)
        return config.get('optional_services', [])
    
    def get_document_types(self, case_type_id: str) -> list:
        """Get document types configuration for a case type"""
        config = self.get_case_type_config(case_type_id)
        return config.get('document_types', [])
    
    def get_service_fee(self, service_id: str) -> float:
        """Get fee for a specific service from global or case-specific services"""
        if not self.config:
            return 0.00
        
        # Check global optional services first
        global_services = self.config.get('global_optional_services', [])
        for service in global_services:
            if service.get('id') == service_id:
                return float(service.get('fee', 0.00))
        
        # Could also check case-specific services here if needed
        return 0.00


# Global instance
case_type_config = CaseTypeConfig()
