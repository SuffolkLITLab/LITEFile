# models.py - Optional extension to store additional user information
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserProfile(AbstractUser):
    """
    Extended user profile to store eFile registration information.
    """

    # TODO(brycew): what happens if someone is trying to do stuff in multiple jurisdictions?
    tyler_jurisdiction = models.CharField(max_length=20)
    tyler_user_id = models.CharField(max_length=100, blank=True, null=True)

    # TODO(brycew): uncomment when https://github.com/SuffolkLITLab/EfileProxyServer/issues/334 is in
    # token_expires_at = models.DateTimeField(blank=True, null=True)

    # Communication Preferences
    email_updates = models.BooleanField(default=False)
    text_updates = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


class FilingDraft(models.Model):
    """Durable aggregate for a single in-progress or submitted court filing."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTING = "submitting", "Submitting"
        SUBMITTED = "submitted", "Submitted"
        ERROR = "error", "Error"
        ABANDONED = "abandoned", "Abandoned"

    class WorkflowStep(models.TextChoices):
        OPTIONS = "options", "Options"
        UPLOAD_FIRST = "upload_first", "Upload lead document"
        CASE_INFORMATION = "case_information", "Case information"
        DOCUMENTS = "documents", "Documents"
        PAYMENT = "payment", "Payment"
        REVIEW = "review", "Review"
        CONFIRMATION = "confirmation", "Confirmation"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="filing_drafts",
    )
    session_key = models.CharField(max_length=80, blank=True, db_index=True)
    session_id = models.CharField(max_length=100, blank=True, db_index=True)
    jurisdiction = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    current_step = models.CharField(max_length=64, choices=WorkflowStep.choices, default=WorkflowStep.OPTIONS)

    existing_case = models.CharField(max_length=20, blank=True)
    court_code = models.CharField(max_length=100, blank=True)
    court_name = models.CharField(max_length=255, blank=True)
    case_category_code = models.CharField(max_length=100, blank=True)
    case_category_name = models.CharField(max_length=255, blank=True)
    case_type_code = models.CharField(max_length=100, blank=True)
    case_type_name = models.CharField(max_length=255, blank=True)
    case_subtype_code = models.CharField(max_length=100, blank=True)
    case_subtype_name = models.CharField(max_length=255, blank=True)
    filing_type_code = models.CharField(max_length=100, blank=True)
    filing_type_name = models.CharField(max_length=255, blank=True)
    document_type_code = models.CharField(max_length=100, blank=True)
    document_type_name = models.CharField(max_length=255, blank=True)

    previous_case_id = models.CharField(max_length=255, blank=True)
    docket_number = models.CharField(max_length=255, blank=True)

    selected_payment_account_id = models.CharField(max_length=255, blank=True)
    selected_payment_account_name = models.CharField(max_length=255, blank=True)

    optional_services = models.JSONField(default=list, blank=True)
    extracted_guesses = models.JSONField(default=dict, blank=True)
    extra_case_data = models.JSONField(default=dict, blank=True)
    submission_response = models.JSONField(default=dict, blank=True)

    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["jurisdiction", "status"]),
            models.Index(fields=["status", "updated_at"]),
        ]

    def __str__(self):
        return f"{self.get_status_display()} filing draft #{self.pk} ({self.jurisdiction})"

    def mark_submitted(self, response_data):
        self.status = self.Status.SUBMITTED
        self.current_step = self.WorkflowStep.CONFIRMATION
        self.submission_response = response_data or {}
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "current_step", "submission_response", "submitted_at", "updated_at"])

    def mark_error(self, response_data):
        self.status = self.Status.ERROR
        self.submission_response = response_data or {}
        self.save(update_fields=["status", "submission_response", "updated_at"])


class FilingDocument(models.Model):
    """Uploaded document that belongs to a filing draft."""

    class Role(models.TextChoices):
        LEAD = "lead", "Lead document"
        SUPPORTING = "supporting", "Supporting document"

    draft = models.ForeignKey(FilingDraft, on_delete=models.CASCADE, related_name="documents")
    role = models.CharField(max_length=20, choices=Role.choices)
    sort_order = models.PositiveIntegerField(default=0)

    name = models.CharField(max_length=255, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    size = models.PositiveBigIntegerField(blank=True, null=True)
    content_type = models.CharField(max_length=255, blank=True)
    s3_key = models.CharField(max_length=1024, blank=True)
    public_url = models.URLField(max_length=2048, blank=True)

    filing_type_code = models.CharField(max_length=100, blank=True)
    filing_type_name = models.CharField(max_length=255, blank=True)
    document_type_code = models.CharField(max_length=100, blank=True)
    document_type_name = models.CharField(max_length=255, blank=True)
    filing_component_code = models.CharField(max_length=100, blank=True)
    filing_component_name = models.CharField(max_length=255, blank=True)

    courtesy_copy_email = models.EmailField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["draft", "role", "sort_order"], name="unique_document_order_per_draft_role"),
        ]

    def __str__(self):
        return self.name or f"{self.get_role_display()} for draft #{self.draft_id}"


class FilingParty(models.Model):
    """Person or organization associated with a filing draft."""

    draft = models.ForeignKey(FilingDraft, on_delete=models.CASCADE, related_name="parties")
    role = models.CharField(max_length=50)
    sort_order = models.PositiveIntegerField(default=0)

    party_type = models.CharField(max_length=100, blank=True)
    external_party_id = models.CharField(max_length=255, blank=True)

    first_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    suffix = models.CharField(max_length=50, blank=True)
    organization_name = models.CharField(max_length=255, blank=True)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="US", blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["draft", "role", "sort_order"], name="unique_party_order_per_draft_role"),
        ]
        verbose_name_plural = "Filing parties"

    def __str__(self):
        display_name = " ".join(part for part in [self.first_name, self.middle_name, self.last_name] if part)
        return display_name or self.organization_name or f"{self.role} for draft #{self.draft_id}"
