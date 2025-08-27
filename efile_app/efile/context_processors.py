"""
Context processors for jurisdiction-aware templates
"""


def jurisdiction_context(request):
    """Add current jurisdiction to all template contexts"""
    current_jurisdiction = request.session.get("jurisdiction", "illinois")

    jurisdiction_configs = {
        "illinois": {
            "name": "Illinois eFile",
            "code": "illinois",
            "display_name": "Illinois",
            "icon": "fas fa-balance-scale",
            "api_endpoint": "/api/illinois/",
            "config_file": "illinois.yaml",
        },
        "massachusetts": {
            "name": "Massachusetts eFile",
            "code": "massachusetts",
            "display_name": "Massachusetts",
            "icon": "fas fa-balance-scale",
            "api_endpoint": "/api/massachusetts/",
            "config_file": "massachusetts.yaml",
        },
    }

    return {
        "current_jurisdiction": current_jurisdiction,
        "jurisdiction_config": jurisdiction_configs.get(current_jurisdiction, jurisdiction_configs["illinois"]),
        "available_jurisdictions": jurisdiction_configs,
    }
