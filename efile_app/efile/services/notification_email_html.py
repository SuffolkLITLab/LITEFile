"""Email-safe progress graphics for the proxy's HTML-capable SendGrid transport."""

from html import escape

from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from efile.services.filings import filing_tracker


def _progress(status):
    return render_to_string("efile/emails/filing_progress.html", {"tracker": filing_tracker(status)}).strip()


def _neutral_progress():
    # The callback provides a display label, not reliably a raw status code.
    # Only show progress for explicit known values; do not guess unknown stages.
    choices = {
        "submitting": ("submitting", "in progress"),
        "submitted": ("submitted", "received by the e-filing system"),
        "receipted": ("receipted", "received by the court"),
        "under-review": ("under-review", "under review"),
        "reviewed": ("reviewed",),
        "returned": ("returned", "returned for changes", "returned to filer"),
    }
    parts = []
    for index, (status, labels) in enumerate(choices.items()):
        condition = " or ".join(f'status|lower == "{label}"' for label in labels)
        parts.append("{% " + ("if" if index == 0 else "elif") + " " + condition + " %}")
        parts.append(_progress(status))
    parts.append("{% endif %}")
    return "".join(parts)


def render_notification_email(field, contents, tracker_url):
    status = {
        "email_confirmation_contents": "submitted",
        "acceptance_contents": "accepted",
        "rejected_contents": "returned",
    }.get(field)
    progress = _progress(status) if status else _neutral_progress()
    # Text-node escaping leaves quotes intact for the server-owned Jinjava
    # conditions. Interpolated data has already had template delimiters encoded.
    # URL attributes are escaped separately, including quotes.
    body = escape(contents, quote=False).replace("\n", "<br>")
    link = f'<a href="{escape(tracker_url, quote=True)}" style="color:#003c71;text-decoration:underline;">View filing status and next steps</a>'
    body = body.replace(escape(tracker_url, quote=False), link)
    # Both fragments are escaped text or rendered, repository-owned markup.
    safe_body = mark_safe(body)  # nosec
    safe_progress = mark_safe(progress)  # nosec
    return render_to_string(
        "efile/emails/filing_notification.html",
        {"body": safe_body, "progress": safe_progress},
    ).strip()
