"""
Jurisdiction management views
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ..utils.config_loader import config_loader


@require_POST
def switch_jurisdiction(request):
    """Switch user's jurisdiction preference"""
    try:
        data = json.loads(request.body)
        jurisdiction = data.get("jurisdiction")

        # Validate jurisdiction
        valid_jurisdictions = config_loader.get_available_jurisdictions()
        if jurisdiction not in valid_jurisdictions:
            return JsonResponse({"error": "Invalid jurisdiction"}, status=400)

        # Update session
        request.session["jurisdiction"] = jurisdiction
        request.session.modified = True

        return JsonResponse(
            {"success": True, "jurisdiction": jurisdiction, "message": f"Switched to {jurisdiction.title()}"}
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def get_current_jurisdiction(request):
    """Get current jurisdiction info"""
    current_jurisdiction = request.session.get("jurisdiction", "illinois")

    return JsonResponse(
        {
            "jurisdiction": current_jurisdiction,
            "config": config_loader.get_short_jurisdiction_config(current_jurisdiction),
        }
    )
