"""
API views for form configuration based on case-type-forms.yaml
"""

import logging
import os

import yaml
from django.views.decorators.http import require_http_methods

from .base import APIResponseMixin

logger = logging.getLogger(__name__)


class ConfigAPIViews(APIResponseMixin):
    """API views for form configuration"""

    @staticmethod
    def _load_case_type_forms():
        """Load case type forms configuration from YAML"""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "static", "config", "case-type-forms.yaml"
            )

            with open(config_path) as file:
                return yaml.safe_load(file)
        except Exception as e:
            logger.exception("Error loading case-type-forms.yaml: %s", e)
            return None

    @staticmethod
    def _find_case_type_by_keywords(case_type_name):
        """Find case type configuration by matching keywords"""
        forms_config = ConfigAPIViews._load_case_type_forms()
        if not forms_config or "case_types" not in forms_config:
            return None

        case_type_name_lower = case_type_name.lower()

        # Try exact match first
        if case_type_name_lower in forms_config["case_types"]:
            return forms_config["case_types"][case_type_name_lower]

        # Try keyword matching
        for _case_type_key, case_type_config in forms_config["case_types"].items():
            if "keywords" in case_type_config:
                for keyword in case_type_config["keywords"]:
                    if keyword.lower() in case_type_name_lower:
                        return case_type_config

        return None

    @staticmethod
    @require_http_methods(["GET"])
    def get_form_config(request):
        """Get complete form configuration for a specific filing type"""
        try:
            # Get required parameters
            # NOTE: temporarily commenting out the unused variables
            # category_id = request.GET.get("category")
            case_type_id = request.GET.get("case_type")
            # filing_type_id = request.GET.get("filing_type")

            if not case_type_id:
                return ConfigAPIViews.error_response("Missing required parameter: case_type")

            # Try to find case type configuration using case_type_id as the name
            case_config = ConfigAPIViews._find_case_type_by_keywords(case_type_id)

            # If no specific configuration found, return minimal structure
            if not case_config:
                return ConfigAPIViews.success_response(
                    {
                        "sections": {},
                        "is_name_change": "name change" in case_type_id.lower(),
                        "case_type_name": case_type_id,
                        "has_parties": False,
                    }
                )

            # Structure the response based on case-type-forms.yaml format
            config = {
                "sections": case_config.get("sections", {}),
                "is_name_change": "name change" in case_type_id.lower(),
                "case_type_name": case_type_id,
                "has_parties": len(case_config.get("sections", {})) > 0,
            }

            return ConfigAPIViews.success_response(config)

        except Exception as e:
            return ConfigAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
get_form_config = ConfigAPIViews.get_form_config
