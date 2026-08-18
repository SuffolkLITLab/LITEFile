"""
Context processors for jurisdiction-aware templates
"""

from .utils.config_loader import config_loader


def jurisdiction_context(request):
    """Add current jurisdiction and its config to all template contexts."""

    # For templates, only use the jurisdiction if it is explicitly present in
    # the URL path (e.g. /jurisdiction/illinois/...) or GET params.
    # Do not bleed session jurisdiction into generic root routes like /about/ or /choose-jurisdiction.
    current_jurisdiction = None
    if request.GET.get("jurisdiction"):
        current_jurisdiction = request.GET.get("jurisdiction").lower()
    else:
        segments = request.path.split("/")
        if len(segments) >= 3 and segments[1] == "jurisdiction":
            current_jurisdiction = segments[2].lower()

    config = config_loader.load_jurisdiction_config(current_jurisdiction)

    return {
        "jurisdiction": current_jurisdiction,
        "config": config,
    }
