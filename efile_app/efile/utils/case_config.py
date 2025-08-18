"""
Case Types Configuration Utility

This module provides utilities for reading and processing the YAML configuration
file that defines case types, required parties, and form structures.
"""

import yaml
import os
from django.conf import settings
from typing import Dict, List, Optional, Any


class CaseTypesConfig:
    """Handles loading and processing of case types configuration from YAML file."""
    
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
    
    def load_config(self) -> None:
        """Load the YAML configuration file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML configuration: {e}")
    
    def get_case_categories(self) -> List[Dict[str, str]]:
        """Get all available case categories."""
        if not self.config or 'case_categories' not in self.config:
            return []
        
        categories = []
        for key, category in self.config['case_categories'].items():
            categories.append({
                'value': key,
                'text': category['name'],
                'description': category.get('description', '')
            })
        
        return categories
    
    def get_case_types(self, category_id: str) -> List[Dict[str, str]]:
        """Get case types for a specific category."""
        if not self.config or 'case_categories' not in self.config:
            return []
        
        category = self.config['case_categories'].get(category_id)
        if not category or 'case_types' not in category:
            return []
        
        case_types = []
        for key, case_type in category['case_types'].items():
            case_types.append({
                'value': key,
                'text': case_type['name'],
                'description': case_type.get('description', '')
            })
        
        return case_types
    
    def get_filing_types(self, category_id: str, case_type_id: str) -> List[Dict[str, str]]:
        """Get filing types for a specific case type."""
        if not self.config or 'case_categories' not in self.config:
            return []
        
        category = self.config['case_categories'].get(category_id)
        if not category or 'case_types' not in category:
            return []
        
        case_type = category['case_types'].get(case_type_id)
        if not case_type or 'filing_types' not in case_type:
            return []
        
        filing_types = []
        for key, filing_type in case_type['filing_types'].items():
            filing_types.append({
                'value': key,
                'text': filing_type['name']
            })
        
        return filing_types
    
    def get_document_types(self, category_id: str, case_type_id: str, filing_type_id: str, county: str = None) -> List[Dict[str, str]]:
        """Get document types for a specific filing type, optionally filtered by county."""
        document_types = []
        
        # Get specific document types for this filing type
        filing_type_config = self._get_filing_type_config(category_id, case_type_id, filing_type_id)
        if filing_type_config and 'document_types' in filing_type_config:
            document_types.extend(filing_type_config['document_types'])
        
        # Add default document types
        if self.config and 'default_document_types' in self.config:
            document_types.extend(self.config['default_document_types'])
        
        return document_types
    
    def get_required_parties(self, category_id: str, case_type_id: str, filing_type_id: str) -> List[Dict[str, Any]]:
        """Get required parties configuration for a specific filing type."""
        filing_type_config = self._get_filing_type_config(category_id, case_type_id, filing_type_id)
        if filing_type_config and 'required_parties' in filing_type_config:
            return filing_type_config['required_parties']
        return []
    
    def get_optional_services(self, category_id: str, case_type_id: str, filing_type_id: str) -> List[Dict[str, Any]]:
        """Get optional services for a specific filing type."""
        services = []
        
        # Get specific services for this filing type
        filing_type_config = self._get_filing_type_config(category_id, case_type_id, filing_type_id)
        if filing_type_config and 'optional_services' in filing_type_config:
            services.extend(filing_type_config['optional_services'])
        
        # Add global optional services
        if self.config and 'global_optional_services' in self.config:
            services.extend(self.config['global_optional_services'])
        
        return services
    
    def _get_filing_type_config(self, category_id: str, case_type_id: str, filing_type_id: str) -> Optional[Dict[str, Any]]:
        """Get the configuration for a specific filing type."""
        if not self.config or 'case_categories' not in self.config:
            return None
        
        category = self.config['case_categories'].get(category_id)
        if not category or 'case_types' not in category:
            return None
        
        case_type = category['case_types'].get(case_type_id)
        if not case_type or 'filing_types' not in case_type:
            return None
        
        return case_type['filing_types'].get(filing_type_id)
    
    def get_form_config(self, category_id: str, case_type_id: str, filing_type_id: str) -> Dict[str, Any]:
        """Get complete form configuration for a specific filing type."""
        return {
            'required_parties': self.get_required_parties(category_id, case_type_id, filing_type_id),
            'optional_services': self.get_optional_services(category_id, case_type_id, filing_type_id),
            'document_types': self.get_document_types(category_id, case_type_id, filing_type_id)
        }
    
    def validate_selection(self, category_id: str, case_type_id: str = None, filing_type_id: str = None) -> Dict[str, bool]:
        """Validate that the selected options exist in the configuration."""
        validation = {
            'category_valid': False,
            'case_type_valid': False,
            'filing_type_valid': False
        }
        
        if not self.config or 'case_categories' not in self.config:
            return validation
        
        # Validate category
        if category_id in self.config['case_categories']:
            validation['category_valid'] = True
            category = self.config['case_categories'][category_id]
            
            # Validate case type
            if case_type_id and 'case_types' in category:
                if case_type_id in category['case_types']:
                    validation['case_type_valid'] = True
                    case_type = category['case_types'][case_type_id]
                    
                    # Validate filing type
                    if filing_type_id and 'filing_types' in case_type:
                        if filing_type_id in case_type['filing_types']:
                            validation['filing_type_valid'] = True
        
        return validation


# Global instance
case_types_config = CaseTypesConfig()
