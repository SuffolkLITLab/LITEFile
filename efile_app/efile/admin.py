from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import FilingDocument, FilingDraft, FilingParty, UserProfile


class FilingDocumentInline(admin.TabularInline):
    model = FilingDocument
    extra = 0
    fields = (
        "role",
        "sort_order",
        "name",
        "filing_type_code",
        "document_type_code",
        "filing_component_code",
        "public_url",
    )
    readonly_fields = ("created_at", "updated_at")


class FilingPartyInline(admin.TabularInline):
    model = FilingParty
    extra = 0
    fields = ("role", "sort_order", "party_type", "first_name", "last_name", "email", "phone")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserProfile)
class UserProfileAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "eFile profile",
            {
                "fields": (
                    "tyler_jurisdiction",
                    "tyler_user_id",
                    "email_updates",
                    "text_updates",
                )
            },
        ),
    )
    list_display = ("username", "email", "tyler_jurisdiction", "tyler_user_id", "is_staff")


@admin.register(FilingDraft)
class FilingDraftAdmin(admin.ModelAdmin):
    inlines = [FilingDocumentInline, FilingPartyInline]
    list_display = (
        "id",
        "user",
        "jurisdiction",
        "status",
        "current_step",
        "court_code",
        "case_type_code",
        "updated_at",
    )
    list_filter = ("jurisdiction", "status", "current_step", "created_at", "updated_at")
    search_fields = (
        "id",
        "session_id",
        "court_code",
        "court_name",
        "case_type_code",
        "case_type_name",
        "docket_number",
        "previous_case_id",
        "user__username",
        "user__email",
    )
    readonly_fields = ("created_at", "updated_at", "submitted_at")


@admin.register(FilingDocument)
class FilingDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "draft", "role", "sort_order", "name", "document_type_code", "updated_at")
    list_filter = ("role", "content_type", "created_at", "updated_at")
    search_fields = ("name", "original_filename", "s3_key", "public_url", "draft__id")


@admin.register(FilingParty)
class FilingPartyAdmin(admin.ModelAdmin):
    list_display = ("id", "draft", "role", "party_type", "first_name", "last_name", "email")
    list_filter = ("role", "party_type", "created_at", "updated_at")
    search_fields = ("first_name", "middle_name", "last_name", "organization_name", "email", "draft__id")
