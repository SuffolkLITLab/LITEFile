"""Logging is configured before Django's model registry is ready."""

import logging

from django.conf import settings


class StaffLogRedactionFilter(logging.Filter):
    def filter(self, record):
        request = getattr(record, "request", None)
        path = getattr(request, "path", "")
        prefix = f"/{settings.LITEFILE_STAFF_PATH}/"
        if path.startswith(prefix) or prefix in record.getMessage():
            record.msg = "Staff request completed with HTTP status %s"
            record.args = (getattr(record, "status_code", "unknown"),)
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True
