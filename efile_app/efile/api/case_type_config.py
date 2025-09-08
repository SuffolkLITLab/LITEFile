from django.http import JsonResponse

from .case_form_views import CaseFormAPIViews


def get_case_type_config(request):
    """
    Serves the case type configuration from jurisdiction-aware configuration system
    """
    try:
        jurisdiction = request.GET.get("jurisdiction") or request.session.get("jurisdiction", "illinois")

        # Use the new jurisdiction-aware configuration loader
        config_data = CaseFormAPIViews._load_jurisdiction_configuration(jurisdiction)

        # Process case types to ensure proper inheritance from base_case_types
        processed_case_types = {}

        # First, add all base case types
        if "base_case_types" in config_data:
            for key, value in config_data["base_case_types"].items():
                processed_case_types[key] = value.copy()

        # Then, merge jurisdiction-specific case types
        if "case_types" in config_data:
            for key, value in config_data["case_types"].items():
                if key in processed_case_types:
                    # Merge jurisdiction config with base config
                    base_config = processed_case_types[key]
                    jurisdiction_config = value.copy()

                    # Deep merge the configurations
                    merged_config = CaseFormAPIViews._deep_merge_configs(base_config, jurisdiction_config)
                    processed_case_types[key] = merged_config
                else:
                    # New case type not in base
                    processed_case_types[key] = value.copy()

        # Transform to match expected format for backward compatibility
        response_data = {
            "jurisdiction": jurisdiction,
            "case_types": processed_case_types,
            "base_case_types": config_data.get("base_case_types", {}),
            "defaults": config_data.get("defaults", {}),
            "court_specific_requirements": config_data.get("court_specific_requirements", {}),
        }

        return JsonResponse({"success": True, "config": response_data})

    except Exception as e:
        return JsonResponse({"success": False, "error": f"Configuration loading error: {str(e)}"}, status=500)
