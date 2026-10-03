"""Restricted operational work and permanent, identifier-free usage counters."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class StaffRoleGrant(models.Model):
    class Role(models.TextChoices):
        ACCOUNTS = "accounts", "Account management"
        ANALYTICS = "analytics", "Aggregate reporting"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_roles")
    jurisdiction = models.CharField(max_length=40)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "jurisdiction", "role"], name="staff_role_scope")]

    def clean(self):
        from efile.utils.config_loader import config_loader

        if self.jurisdiction not in config_loader.get_available_jurisdictions():
            raise ValidationError("Choose a configured jurisdiction.")
        if self.user_id and (not self.user.is_staff or not self.user.is_active):
            raise ValidationError("Roles require an active staff account.")

    def __str__(self):
        return f"Staff #{self.user_id}: {self.jurisdiction} / {self.get_role_display()}"


class PrivacyRequest(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        VERIFIED = "verified", "Verified"
        PROCESSING = "processing", "Processing"
        ATTENTION = "attention", "Needs attention"
        COMPLETED = "completed", "Live-system deletion completed"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    jurisdiction = models.CharField(max_length=40)
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="privacy_requests"
    )
    account_wide = models.BooleanField(default=False)
    draft_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="handled_privacy_requests"
    )
    verified_at = models.DateTimeField(null=True)
    # Restricted retry manifest. Cleared only after storage and database cleanup.
    object_keys = models.JSONField(default=list)
    deleted_keys = models.JSONField(default=list)
    counts = models.JSONField(default=dict)
    outcome = models.CharField(max_length=40, blank=True)
    external_cleanup_pending = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True)


class StaffAudit(models.Model):
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reference = models.UUIDField(null=True)
    jurisdiction = models.CharField(max_length=40)
    action = models.CharField(max_length=40)
    outcome = models.CharField(max_length=40)
    counts = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class StaffLoginThrottle(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveIntegerField(default=0)
    window_started = models.DateTimeField()


class StoredUpload(models.Model):
    """Keep object ownership after a document is removed or replaced."""

    draft = models.ForeignKey("efile.FilingDraft", on_delete=models.CASCADE, related_name="stored_uploads")
    key = models.CharField(max_length=1024, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["draft", "key"], name="stored_upload_owner")]


class UsageCounter(models.Model):
    day = models.DateField()
    granularity = models.CharField(max_length=5, default="day")
    jurisdiction = models.CharField(max_length=40)
    metric = models.CharField(max_length=40)
    filing_kind = models.CharField(max_length=10)
    dimension = models.CharField(max_length=40, default="all")
    value = models.CharField(max_length=80, default="all")
    count = models.PositiveBigIntegerField(default=0)
    contributors = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["day", "granularity", "jurisdiction", "metric", "filing_kind", "dimension", "value"],
                name="usage_counter_bucket",
            )
        ]
        indexes = [models.Index(fields=["jurisdiction", "day"], name="usage_scope_day")]


class UsageEvent(models.Model):
    draft = models.ForeignKey("efile.FilingDraft", on_delete=models.CASCADE)
    metric = models.CharField(max_length=40)
    operation = models.CharField(max_length=80, default="once")
    dimensions = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    counted_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["draft", "metric", "operation"], name="usage_event_once")]


class UsageContributor(models.Model):
    """Operational deduplication only; removed with the contributing account."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    counter = models.ForeignKey(UsageCounter, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "counter"], name="usage_contributor_once")]


class UsageMatter(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    jurisdiction = models.CharField(max_length=40)
    identity = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "jurisdiction", "identity"], name="usage_matter_once")]
