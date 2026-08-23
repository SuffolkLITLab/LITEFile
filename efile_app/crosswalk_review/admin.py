from django.contrib import admin

from .models import CrosswalkForm, CrosswalkMapping, MappingVerdict


@admin.register(CrosswalkForm)
class CrosswalkFormAdmin(admin.ModelAdmin):
    list_display = ["canonical_id", "jurisdiction", "canonical_name", "department", "is_efileable"]
    search_fields = ["canonical_id", "canonical_name", "form_id", "jurisdiction"]
    list_filter = ["jurisdiction", "is_efileable", "is_form"]
    readonly_fields = ["canonical_id", "raw_data"]


@admin.register(CrosswalkMapping)
class CrosswalkMappingAdmin(admin.ModelAdmin):
    list_display = ["form", "mapping_index", "category", "case_type", "filing_type", "confidence", "catalog_status"]
    search_fields = ["form__canonical_id", "category", "case_type", "filing_type"]
    list_filter = ["catalog_status", "association_status", "filing_phase"]
    readonly_fields = ["raw_data"]


@admin.register(MappingVerdict)
class MappingVerdictAdmin(admin.ModelAdmin):
    list_display = ["mapping", "reviewer_name", "verdict", "created_at", "updated_at"]
    search_fields = ["reviewer_name", "mapping__form__canonical_id"]
    list_filter = ["verdict", "reviewer_name"]
    readonly_fields = ["created_at", "updated_at"]
