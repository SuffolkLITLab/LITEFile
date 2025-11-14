"""
API views for form configuration based on jurisdiction-aware configuration system
Uses base-case-types.yaml and state-specific overrides
"""

import logging

from django.views.decorators.http import require_http_methods

from ..utils.config_loader import config_loader
from .base import APIResponseMixin

logger = logging.getLogger(__name__)


class ConfigAPIViews(APIResponseMixin):
    """API views for form configuration - delegates to config_loader for jurisdiction-aware configs"""

    @staticmethod
    @require_http_methods(["GET"])
    def get_form_config(request):
        """Get complete form configuration for a specific filing type"""
        try:
            # Get required parameters
            category_id = request.GET.get("category")
            case_type_id = request.GET.get("case_type")
            filing_type_id = request.GET.get("filing_type")
            court_code = request.GET.get("court")
            jurisdiction = request.GET.get("jurisdiction") or request.session.get("jurisdiction", "illinois")

            logger.debug(
                f"Fetching form config for "
                f"category: {category_id} case type: {case_type_id} court: {court_code}"
                f"jurisdiction: {jurisdiction} filing type: {filing_type_id}"
            )

            if not case_type_id:
                return ConfigAPIViews.error_response("Missing required parameter: case_type")

            # Use the new jurisdiction-aware configuration system
            case_config = config_loader.get_case_type_config(jurisdiction, case_type_id, court=court_code)

            # If no specific configuration found, return minimal structure
            if not case_config:
                return ConfigAPIViews.success_response(
                    {
                        "sections": {},
                        "is_name_change": "name change" in case_type_id.lower(),
                        "case_type_name": case_type_id,
                        "has_parties": False,
                        "jurisdiction": jurisdiction,
                    }
                )

            sections = case_config.get("sections", {})

            # Structure the response in the expected format
            config = {
                "sections": sections,
                "is_name_change": "name change" in case_type_id.lower(),
                "case_type_name": case_type_id,
                "has_parties": len(sections) > 0,
                "jurisdiction": jurisdiction,
                "description": case_config.get("description", ""),
                "validation_rules": case_config.get("validation_rules", []),
            }

            return ConfigAPIViews.success_response(config)

        except Exception as e:
            return ConfigAPIViews.error_response(f"Error: {str(e)}")


# Individual view functions for URL mapping
get_form_config = ConfigAPIViews.get_form_config
