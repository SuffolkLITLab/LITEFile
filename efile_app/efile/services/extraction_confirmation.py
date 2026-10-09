"""Remember review of one document's findings, independently of case edits."""

import hashlib
import json

from efile.models import DocumentExtraction, FilingDocument


def extraction_review_fingerprint(draft):
    lead = FilingDocument.objects.filter(draft=draft, role=FilingDocument.Role.LEAD).first()
    extraction = DocumentExtraction.objects.filter(document=lead).first() if lead else None
    source = {
        "document": [lead.pk, lead.s3_key, lead.original_s3_key] if lead else None,
        "extraction": [extraction.pk, str(extraction.updated_at)] if extraction else None,
        "findings": draft.extracted_guesses or {},
    }
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def extraction_is_confirmed(draft):
    return bool(draft.extraction_review_fingerprint) and (
        draft.extraction_review_fingerprint == extraction_review_fingerprint(draft)
    )
