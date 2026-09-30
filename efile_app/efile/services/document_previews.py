"""Server-owned preview acknowledgements tied to the current filing bytes."""

import hashlib
import json


def unreviewed_documents(draft):
    return draft.documents.filter(preparation_reviewed_at__isnull=True)


def preview_fingerprint(documents):
    return hashlib.sha256(
        json.dumps(
            sorted(
                (doc.pk, doc.s3_key, doc.original_s3_key, doc.preparation, doc.size, str(doc.updated_at))
                for doc in documents
            )
        ).encode()
    ).hexdigest()


def require_document_previews(draft):
    if draft.documents.filter(preparation="").exists() or unreviewed_documents(draft).exists():
        raise ValueError(
            "Preview your uploaded PDFs and confirm that their pages and signatures are correct before submitting."
        )


def document_storage_keys(document):
    return list(dict.fromkeys(key for key in (document.s3_key, document.original_s3_key) if key))
