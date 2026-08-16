# models.py - Optional extension to store additional user information
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from efile.workflow import ExistingCase, WorkflowStepKey, get_workflow_step_choices


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


class FilingPlan(models.Model):
    """A filer's long-lived matter: the documents they are gathering for it.

    A plan outlives any one envelope. It stores what the filer's case *is* in
    semantic terms -- the court, case category, case type, and lead filing type
    by name -- and never the court's numeric codes for them. Those codes belong
    to a filing: they differ per court and change without notice, so a later
    filing resolves the stored names against the live code lists instead of
    trusting a code saved months ago.

    ``checklist`` is a snapshot of the configured guidance, taken when the plan
    is created, plus the filer's own progress. Snapshotting means a partner
    editing the YAML later does not silently rewrite a checklist someone is
    already working through.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="filing_plans",
    )
    title = models.CharField(max_length=255)
    jurisdiction = models.CharField(max_length=40, db_index=True)

    court_code = models.CharField(max_length=100, blank=True)
    court_name = models.CharField(max_length=255, blank=True)
    case_category_name = models.CharField(max_length=255, blank=True)
    case_type_name = models.CharField(max_length=255, blank=True)
    lead_filing_type_name = models.CharField(max_length=255, blank=True)

    # {item_id: {"label": str, "requirement": "always|usually|sometimes",
    #            "description": str (optional), "complete": bool}}
    checklist = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "jurisdiction"], name="plan_user_jurisdiction_idx"),
        ]

    def __str__(self):
        return self.title or f"Filing plan #{self.pk}"


class FilingDraft(models.Model):
    """Durable aggregate for a single in-progress or submitted court filing."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTING = "submitting", "Submitting"
        SUBMITTED = "submitted", "Submitted"
        ERROR = "error", "Error"
        ABANDONED = "abandoned", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="filing_drafts",
    )
    # The matter this filing belongs to, when the filer has one. A plan can
    # gather several filings over time; losing the plan must not lose the filing.
    plan = models.ForeignKey(
        "FilingPlan",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="filing_drafts",
    )
    jurisdiction = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    current_step = models.CharField(
        max_length=64,
        choices=get_workflow_step_choices(),
        default=WorkflowStepKey.OPTIONS,
    )
    workflow_version = models.PositiveSmallIntegerField(default=2)

    existing_case = models.CharField(
        max_length=20,
        choices=[(value.value, value.name.title()) for value in ExistingCase],
        blank=True,
    )
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
    case_title = models.CharField(max_length=500, blank=True)

    selected_payment_account_id = models.CharField(max_length=255, blank=True)
    selected_payment_account_name = models.CharField(max_length=255, blank=True)
    # Tyler's paymentAccountTypeCode for the selected account (e.g. "WV" for a fee
    # waiver). Drives whether Review shows a fee total or waiver messaging.
    selected_payment_account_type = models.CharField(max_length=50, blank=True)
    # The fee quote shown on the Payment step, carried forward so Review can
    # display the same numbers instead of telling the filer to go look again.
    quoted_fee_total = models.CharField(max_length=50, blank=True)
    quoted_fee_breakdown = models.JSONField(default=list, blank=True)

    name_change_reason = models.TextField(blank=True)

    optional_services = models.JSONField(default=list, blank=True)
    extracted_guesses = models.JSONField(default=dict, blank=True)
    document_checklist_acknowledged = models.BooleanField(default=False)
    # The dollar amount at stake, required by the EFSP when any document's
    # filing type is flagged "amountincontroversy: Required". Stored as text
    # (like the fee fields) since it's echoed back to the API rather than
    # computed on.
    amount_in_controversy = models.CharField(max_length=50, blank=True)
    # Area-of-law questionnaire answers (e.g. divorce children questions). These are
    # driven by the per-state/case-type config, not a fixed schema, so they live in a
    # structured JSON field rather than a column each. Only config-defined keys are
    # stored here -- it is not a catch-all for arbitrary case data.
    supplemental_fields = models.JSONField(default=dict, blank=True)
    submission_response = models.JSONField(default=dict, blank=True)

    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="draft_user_status_idx"),
            models.Index(fields=["jurisdiction", "status"], name="draft_jurisdiction_status_idx"),
            models.Index(fields=["status", "updated_at"], name="draft_status_updated_idx"),
        ]

    def __str__(self):
        return f"{self.get_status_display()} filing draft #{self.pk} ({self.jurisdiction})"

    def mark_submitted(self, response_data):
        self.status = self.Status.SUBMITTED
        self.current_step = WorkflowStepKey.CONFIRMATION
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
    # The court's own "amountincontroversy" flag for this document's filing
    # type (from the filing-types codes API) is "Required" for some case
    # types. Recorded per document, since each can carry a different filing
    # type; case_questions asks for the dollar amount if any document needs it.
    filing_requires_amount_in_controversy = models.BooleanField(default=False)

    courtesy_copy_email = models.EmailField(blank=True)
    # Codes selected from the court's optional-services list for this document
    # (e.g. a certified copy), scoped per document since each can have its own
    # filing type. See efile.api.dropdown_views.get_optional_services.
    requested_optional_services = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["draft", "role", "sort_order"], name="unique_document_order_per_draft_role"
            ),
        ]

    def __str__(self):
        return self.name or f"{self.get_role_display()} for draft #{self.draft_id}"


class FilingParty(models.Model):
    """Person or organization associated with a filing draft."""

    draft = models.ForeignKey(FilingDraft, on_delete=models.CASCADE, related_name="parties")
    role = models.CharField(max_length=50)
    sort_order = models.PositiveIntegerField(default=0)

    party_type = models.CharField(max_length=100, blank=True)
    party_type_name = models.CharField(max_length=255, blank=True)
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
