from functools import partial

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Max

from efile.models import FilingDocument, FilingDraft
from efile.services.document_extractions import queue_document_extraction
from efile.services.document_preparation import (
    PreparationError,
    PreparationUnavailable,
    cleanup_unreferenced_uploads,
    cleanup_uploads,
    store_prepared_document,
)
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
                    transaction.on_commit(partial(queue_document_extraction, document), robust=True)
                else:
                    order += 1
            draft.current_step = str(current_step)
            invalidate_fee_quote(draft, save=False)
            draft.save()
    except Exception:
        cleanup_uploads(handler, keys)
        raise
    return read_upload_data(draft)


def prepare_stored_documents(draft, handler):
    """Bring legacy stored uploads through the same preparation and review gate."""
    keys = []
    try:
        with transaction.atomic():
            locked = FilingDraft.objects.select_for_update().get(pk=draft.pk)
            documents = list(locked.documents.filter(preparation=""))
            if not documents:
                return
            if locked.status not in {FilingDraft.Status.DRAFT, FilingDraft.Status.ERROR}:
                raise PreparationError("This filing is no longer available to edit.")
            if not handler._ensure_initialized() or handler.s3_client is None:
                raise PreparationUnavailable("Document storage is unavailable. Please try again later.")
            old_keys = []
            for document in documents:
                if not document.s3_key:
                    raise PreparationError("The stored upload is unavailable. Replace this document before continuing.")
                response = handler.s3_client.get_object(Bucket=handler.bucket_name, Key=document.s3_key)
                body = response["Body"]
                try:
                    content = body.read(settings.MAX_FILE_SIZE + 1)
                finally:
                    body.close()
                old_keys.extend([document.s3_key, document.original_s3_key])
                file = SimpleUploadedFile(document.original_filename or document.name or "document.pdf", content)
                prepared = store_prepared_document(handler, file, draft.jurisdiction, document.role, keys=keys)
                for field, value in prepared.items():
                    setattr(document, field, value)
                document.save()
                if document.role == FilingDocument.Role.LEAD:
                    locked.extracted_guesses = {}
                    transaction.on_commit(partial(queue_document_extraction, document), robust=True)
            invalidate_fee_quote(locked, save=False)
            locked.save()
            transaction.on_commit(partial(cleanup_unreferenced_uploads, old_keys, handler), robust=True)
    except Exception:
        cleanup_uploads(handler, keys)
        raise
