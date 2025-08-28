"""
API views for form configuration based on jurisdiction-aware configuration system
Uses base-case-types.yaml and state-specific overrides
"""

import logging

from django.views.decorators.http import require_http_methods

from .base import APIResponseMixin
from .case_form_views import CaseFormAPIViews

logger = logging.getLogger(__name__)


class ConfigAPIViews(APIResponseMixin):
    """API views for form configuration - delegates to CaseFormAPIViews for jurisdiction-aware configs"""

    @staticmethod
    def _find_config_key_for_case_type(case_type_id, jurisdiction="illinois"):
        """Find the config key (like 'name_change') that corresponds to a case type ID (like '78346')"""
        try:
            config = CaseFormAPIViews._load_jurisdiction_configuration(jurisdiction)
            case_types_sources = [config.get("case_types", {}), config.get("base_case_types", {})]

            case_type_id_lower = case_type_id.lower()

            for case_types in case_types_sources:
                for case_type_key, case_type_config in case_types.items():
                    if "keywords" in case_type_config:
                        for keyword in case_type_config["keywords"]:
                            keyword_lower = keyword.lower()
                            if (
                                keyword_lower in case_type_id_lower
                                or case_type_id_lower in keyword_lower
                                or keyword_lower == case_type_id_lower
                            ):
                                return case_type_key
            return None
        except Exception:
            return None

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
            case_config = CaseFormAPIViews._find_case_type_config(case_type_id, jurisdiction)

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

            # Apply court-specific customizations if they exist
            sections = case_config.get("sections", {})
            if court_code:
                # For court-specific modifications, we need to use the config key (like "name_change")
                # not the case type ID (like "78346"). Find the config key by reverse lookup.
                case_config_key = ConfigAPIViews._find_config_key_for_case_type(case_type_id, jurisdiction)
                sections = CaseFormAPIViews._apply_court_specific_config(
                    sections, court_code, case_config_key or case_type_id, jurisdiction
                )

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
