from django.db import transaction
from django.db.models import Max

from efile.models import FilingDocument, FilingDraft
from efile.services.document_extractions import queue_document_extraction
from efile.services.document_preparation import cleanup_uploads, store_prepared_document
from efile.services.drafts import read_upload_data
from efile.services.fee_quotes import invalidate_fee_quote
from efile.utils.s3_upload_handler import S3UploadHandler
from efile.workflow import WorkflowStepKey


def upload_files(draft, uploaded_files, jurisdiction, *, current_step=WorkflowStepKey.UPLOAD_DOCUMENTS):
    """Prepare and store a whole batch, then queue analysis of the filing copy."""
    handler = S3UploadHandler()
    if not handler._ensure_initialized():
        raise ValueError("Document storage is not configured. Please try again later.")
    keys = []
    try:
        # Prepare the entire batch before changing the durable draft.
        prepared = []
        for file in uploaded_files:
            try:
                prepared.append(store_prepared_document(handler, file, jurisdiction, "document", keys=keys))
            except ValueError as error:
                raise ValueError(f"{file.name}: {error}") from error
        with transaction.atomic():
            draft = FilingDraft.objects.select_for_update().get(pk=draft.pk)
            if draft.status not in {FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR}:
                raise ValueError("This filing is no longer available to edit.")
            has_lead = draft.documents.filter(role=FilingDocument.Role.LEAD).exists()
            highest = draft.documents.filter(role=FilingDocument.Role.SUPPORTING).aggregate(order=Max("sort_order"))[
                "order"
            ]
            order = 0 if highest is None else highest + 1
            for values in prepared:
                is_lead = not has_lead
                document = FilingDocument.objects.create(
                    draft=draft,
                    role=FilingDocument.Role.LEAD if is_lead else FilingDocument.Role.SUPPORTING,
                    sort_order=0 if is_lead else order,
                    **values,
                )
                if is_lead:
                    has_lead = True
                    draft.extracted_guesses = {}
                    queue_document_extraction(document)
                else:
                    order += 1
            draft.current_step = str(current_step)
            invalidate_fee_quote(draft, save=False)
            draft.save()
    except Exception:
        cleanup_uploads(handler, keys)
        raise
    return read_upload_data(draft)
