from django.shortcuts import redirect
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog

from .views.api_views import get_case_data_api, get_filing_components
from .views.choose_jurisdiction import choose_jurisdiction
from .views.confirmation import filing_confirmation
from .views.draft_views import create_draft_view, get_current_draft_view
from .views.expert_form import efile_expert_form
from .views.extraction_review import extraction_review
from .views.filing_path import filing_path
from .views.filing_statuses import filing_statuses
from .views.legacy_workflow import legacy_workflow_redirect
from .views.login import efile_login, efile_logout, efile_password_reset
from .views.options import efile_options
from .views.payment import efile_payment
from .views.register import efile_register
from .views.review import case_review
from .views.session_api import (
    api_save_case_data,
    clear_session_data,
    debug_session_data,
    fetch_and_save_party_type,
    get_upload_data_from_session,
    save_party_type_to_session,
    save_upload_data_to_session,
    save_upload_first_data,
)
from .views.submission import submit_final_filing
from .views.upload import efile_upload
from .views.upload_documents import upload_documents
from .views.upload_first import efile_upload_first


def homepage(request):
    return redirect("efile_choose_jurisdiction")


def jurisdiction_homepage(request, jurisdiction):
    return redirect("efile_login", jurisdiction)


urlpatterns = [
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("", homepage, name="home"),
    path("choose-jurisdiction", choose_jurisdiction, name="efile_choose_jurisdiction"),
    path("jurisdiction/<jurisdiction>", jurisdiction_homepage, name="jurisdiction_homepage"),
    path("jurisdiction/<jurisdiction>/login/", efile_login, name="efile_login"),
    path("jurisdiction/<jurisdiction>/logout/", efile_logout, name="efile_logout"),
    path("jurisdiction/<jurisdiction>/register/", efile_register, name="efile_register"),
    path("jurisdiction/<jurisdiction>/password_reset/", efile_password_reset, name="efile_password_reset"),
    path("jurisdiction/<jurisdiction>/options/", efile_options, name="efile_options"),
    path("jurisdiction/<jurisdiction>/filing-path/", filing_path, name="filing_path"),
    path("jurisdiction/<jurisdiction>/upload-documents/", upload_documents, name="upload_documents"),
    path("jurisdiction/<jurisdiction>/extraction-review/", extraction_review, name="extraction_review"),
    path(
        "jurisdiction/<jurisdiction>/case-lookup/",
        legacy_workflow_redirect,
        {"destination": "case_lookup"},
        name="case_lookup",
    ),
    path(
        "jurisdiction/<jurisdiction>/case-confirmation/",
        legacy_workflow_redirect,
        {"destination": "case_confirmation"},
        name="case_confirmation",
    ),
    path(
        "jurisdiction/<jurisdiction>/document-checklist/",
        legacy_workflow_redirect,
        {"destination": "document_checklist"},
        name="document_checklist",
    ),
    path(
        "jurisdiction/<jurisdiction>/organize-documents/",
        legacy_workflow_redirect,
        {"destination": "organize_documents"},
        name="organize_documents",
    ),
    path(
        "jurisdiction/<jurisdiction>/your-information/",
        legacy_workflow_redirect,
        {"destination": "your_information"},
        name="your_information",
    ),
    path(
        "jurisdiction/<jurisdiction>/parties/",
        legacy_workflow_redirect,
        {"destination": "parties"},
        name="parties",
    ),
    path(
        "jurisdiction/<jurisdiction>/party-details/",
        legacy_workflow_redirect,
        {"destination": "party_details"},
        name="party_details",
    ),
    path(
        "jurisdiction/<jurisdiction>/case-questions/",
        legacy_workflow_redirect,
        {"destination": "case_questions"},
        name="case_questions",
    ),
    path("jurisdiction/<jurisdiction>/drafts/", create_draft_view, name="create_draft"),
    path("jurisdiction/<jurisdiction>/filing_statuses/", filing_statuses, name="filing_statuses"),
    path("jurisdiction/<jurisdiction>/expert_form/", efile_expert_form, name="expert_form"),
    path("jurisdiction/<jurisdiction>/upload_first/", efile_upload_first, name="upload_first"),
    path("jurisdiction/<jurisdiction>/upload/", efile_upload, name="upload"),
    path("jurisdiction/<jurisdiction>/payment/", efile_payment, name="payment"),
    path("jurisdiction/<jurisdiction>/review/", case_review, name="case_review"),
    path("jurisdiction/<jurisdiction>/filing-confirmation/", filing_confirmation, name="filing_confirmation"),
    # Session API endpoints
    path("api/get-case-data/", get_case_data_api, name="get_case_data_api"),
    path("api/get-filing-components/", get_filing_components, name="get_filing_components"),
    path("api/draft/", get_current_draft_view, name="get_current_draft"),
    path("api/save-case-data/", api_save_case_data, name="save_case_data_api"),
    path("api/save-upload-data/", save_upload_data_to_session, name="save_upload_data_to_session"),
    path("api/save-upload-data-first/", save_upload_first_data, name="save_upload_data_to_session"),
    path("api/get-upload-data/", get_upload_data_from_session, name="get_upload_data_from_session"),
    path("api/fetch-party-type/", fetch_and_save_party_type, name="fetch_party_type"),
    path("api/save-party-type/", save_party_type_to_session, name="save_party_type"),
    path("api/submit-final-filing/", submit_final_filing, name="submit_final_filing"),
    path("api/clear-session/", clear_session_data, name="clear_session_data"),
    path("api/debug-session/", debug_session_data, name="debug_session_data"),
    path("api/debug-session-data/", debug_session_data, name="debug_session_data"),
    # API endpoints for dropdowns
    path("api/", include("efile.api.urls")),
    # Legacy endpoints for backward compatibility (can be removed later)
    # path('api/get-case-categories/', views.efile_logout, name='get_case_categories_legacy'),
    # path('api/get-case-types/', views.efile_logout, name='get_case_types_legacy'),
    # path('api/get-filing-types/', views.efile_logout, name='get_filing_types_legacy'),
    # path('api/get-counties/', views.efile_logout, name='get_counties_legacy'),
    # path('api/get-document-types/', views.efile_logout, name='get_document_types_legacy'),
]
