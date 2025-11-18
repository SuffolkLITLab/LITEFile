"""
Context processors for jurisdiction-aware templates
"""

from .utils.config_loader import config_loader


def jurisdiction_context(request):
    """Add current jurisdiction to all template contexts"""
    current_jurisdiction = request.session.get("jurisdiction", "illinois")

    config = config_loader.get_short_jurisdiction_config(current_jurisdiction)
    short_configs = {
        code: config_loader.get_short_jurisdiction_config(code) for code in config_loader.get_available_jurisdictions()
    }

    return {
        "jurisdiction": current_jurisdiction,
        # Returns just a subset of the keys in the config
        "jurisdiction_config": config,
        "available_jurisdictions": short_configs,
    }
