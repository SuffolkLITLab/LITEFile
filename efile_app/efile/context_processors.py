"""
Context processors for jurisdiction-aware templates
"""

from .utils.config_loader import config_loader
from .utils.jurisdiction_stuff import get_jurisdiction_from_request


def jurisdiction_context(request):
    """Add current jurisdiction and its config to all template contexts."""

    current_jurisdiction = get_jurisdiction_from_request(request)
    config = config_loader.load_jurisdiction_config(current_jurisdiction)

    return {
        "jurisdiction": current_jurisdiction,
        "config": config,
    }
