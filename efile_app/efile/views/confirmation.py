from django.shortcuts import render


def filing_confirmation(request, jurisdiction):
    """Confirmation page after successful filing submission."""

    # You can add logic here to retrieve filing details from session
    # or from database if you're storing submitted filings

    context = {
        "jurisdiction": jurisdiction,
        "page_title": "Filing Confirmation",
        "success_message": "Your filing has been successfully submitted!",
    }

    return render(request, "efile/confirmation.html", context)
