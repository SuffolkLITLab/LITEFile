import re
from urllib.parse import urlsplit

from django.db import models


class CrosswalkForm(models.Model):
    """A court form loaded from the crosswalk JSON (read-only reference data)."""

    canonical_id = models.CharField(max_length=200, primary_key=True)
    jurisdiction = models.CharField(max_length=100, blank=True)
    form_id = models.CharField(max_length=200, blank=True)
    canonical_name = models.CharField(max_length=500)
    department = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    is_efileable = models.BooleanField(default=False)
    is_form = models.BooleanField(default=True)
    source_urls = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)

    # Ordering index within the registry so navigation is deterministic
    registry_index = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["registry_index"]
        verbose_name = "Crosswalk form"
        verbose_name_plural = "Crosswalk forms"

    def __str__(self) -> str:
        return f"{self.canonical_id} – {self.canonical_name}"

    @property
    def primary_source_url(self) -> str | None:
        """Return the first safe HTTP(S) source URL, or None."""
        urls = self.safe_source_urls
        return urls[0] if urls else None

    @property
    def safe_source_urls(self) -> list[str]:
        """Return source URLs that are safe to place in links and iframes."""
        safe_urls = []
        for url in self.source_urls or []:
            if not isinstance(url, str):
                continue
            try:
                parsed = urlsplit(url)
            except ValueError:
                continue
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                safe_urls.append(url)
        return safe_urls


class CrosswalkMapping(models.Model):
    """One filing-code mapping for a CrosswalkForm, loaded from JSON."""

    form = models.ForeignKey(CrosswalkForm, on_delete=models.CASCADE, related_name="mappings")
    mapping_index = models.PositiveIntegerField()
    category = models.CharField(max_length=300, blank=True)
    case_type = models.CharField(max_length=300, blank=True)
    filing_type = models.CharField(max_length=500, blank=True)
    filing_phase = models.CharField(max_length=100, blank=True)
    court_names = models.JSONField(default=list)
    confidence = models.FloatField(null=True, blank=True)
    association_status = models.CharField(max_length=100, blank=True)
    catalog_status = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict)

    class Meta:
        ordering = ["form", "mapping_index"]
        unique_together = [("form", "mapping_index")]
        verbose_name = "Crosswalk mapping"
        verbose_name_plural = "Crosswalk mappings"

    def __str__(self) -> str:
        return f"{self.form_id} [{self.mapping_index}] {self.filing_type}"

    @property
    def notes_clean(self) -> str:
        """Return notes with the bracketed [Staging observation: …] suffix stripped."""
        return re.sub(r"\s*\[Staging observation:[^\]]*\]", "", self.notes).strip()

    @property
    def confidence_label(self) -> str:
        if self.confidence is None:
            return "unknown"
        if self.confidence >= 0.85:
            return "high"
        if self.confidence >= 0.60:
            return "medium"
        return "low"

    @property
    def confidence_percent(self) -> float | None:
        """Return the zero-to-one confidence score as a percentage."""
        return self.confidence * 100 if self.confidence is not None else None


class FormReview(models.Model):
    """A reviewer's saved form-identity answers.

    The crosswalk remains read-only reference data. These answers are kept in
    the review database so a reviewer can correct a title or printed form ID
    without silently changing the source crosswalk.
    """

    VERDICT_CHOICES = [
        ("correct", "✓ Correct"),
        ("incorrect", "✗ Incorrect"),
        ("unsure", "? Unsure"),
    ]

    form = models.ForeignKey(CrosswalkForm, on_delete=models.CASCADE, related_name="reviews")
    reviewer_name = models.CharField(max_length=100)
    reviewed_title = models.CharField(max_length=500, blank=True)
    title_verdict = models.CharField(max_length=20, choices=VERDICT_CHOICES, blank=True)
    reviewed_form_id = models.CharField(max_length=200, blank=True)
    form_id_verdict = models.CharField(max_length=20, choices=VERDICT_CHOICES, blank=True)
    reviewer_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["form", "reviewer_name"], name="unique_form_review_reviewer"),
        ]
        ordering = ["-updated_at"]
        verbose_name = "Form review"
        verbose_name_plural = "Form reviews"

    def __str__(self) -> str:
        return f"{self.reviewer_name}: {self.form.canonical_id}"


class MappingVerdict(models.Model):
    """A human reviewer's verdict on one CrosswalkMapping."""

    VERDICT_CHOICES = [
        ("correct", "✓ Correct"),
        ("incorrect", "✗ Incorrect"),
        ("unsure", "? Unsure"),
    ]

    mapping = models.ForeignKey(CrosswalkMapping, on_delete=models.CASCADE, related_name="verdicts")
    reviewer_name = models.CharField(max_length=100)
    verdict = models.CharField(max_length=20, choices=VERDICT_CHOICES, blank=True)
    reviewed_category = models.CharField(max_length=300, blank=True)
    reviewed_case_type = models.CharField(max_length=300, blank=True)
    reviewed_filing_type = models.CharField(max_length=500, blank=True)
    field_verdicts = models.JSONField(default=dict)
    lookup_context = models.JSONField(default=dict)
    reviewer_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("mapping", "reviewer_name")]
        ordering = ["-updated_at"]
        verbose_name = "Mapping verdict"
        verbose_name_plural = "Mapping verdicts"

    def __str__(self) -> str:
        return f"{self.reviewer_name}: {self.verdict} on mapping {self.mapping_id}"
