from django.shortcuts import redirect
from django.urls import include, path

from .views.api_views import get_filing_components
from .views.confirmation import filing_confirmation
from .views.expert_form import efile_expert_form
from .views.jurisdiction import get_current_jurisdiction, switch_jurisdiction
from .views.login import efile_login, efile_logout
from .views.options import efile_options
from .views.register import efile_register
from .views.review import case_review
from .views.session_api import (
    api_get_case_data,
    api_save_case_data,
    clear_session_data,
    debug_session_data,
    fetch_and_save_party_type,
    get_party_types_from_suffolk_api,
    get_upload_data_from_session,
    save_party_type_to_session,
    save_upload_data_to_session,
    save_upload_first_data,
    submit_final_filing,
)
from .views.upload import (
    create_filing,
    efile_upload,
    mock_s3_upload,
    simple_s3_upload,
    test_s3_connection,
)
from .views.upload_first import efile_upload_first


def homepage(request):
    return redirect("efile_login", jurisdiction="illinois")


urlpatterns = [
    path("", homepage, name="home"),
    path("<jurisdiction>/login/", efile_login, name="efile_login"),
    path("<jurisdiction>/logout/", efile_logout, name="efile_logout"),
    path("<jurisdiction>/register/", efile_register, name="efile_register"),
    path("<jurisdiction>/options/", efile_options, name="efile_options"),
    path("<jurisdiction>/expert_form/", efile_expert_form, name="expert_form"),
    path("<jurisdiction>/upload_first/", efile_upload_first, name="upload_first"),
    path("<jurisdiction>/upload/", efile_upload, name="upload"),
    path("<jurisdiction>/review/", case_review, name="case_review"),
    path("<jurisdiction>/filing-confirmation/", filing_confirmation, name="filing_confirmation"),
    # Session API endpoints
    path("api/get-case-data/", api_get_case_data, name="get_case_data_api"),
    path("api/get-filing-components/", get_filing_components, name="get_filing_components"),
    path("api/save-case-data/", api_save_case_data, name="save_case_data_api"),
    path("api/save-upload-data/", save_upload_data_to_session, name="save_upload_data_to_session"),
    path("api/save-upload-data-first/", save_upload_first_data, name="save_upload_data_to_session"),
    path("api/get-upload-data/", get_upload_data_from_session, name="get_upload_data_from_session"),
    path("api/fetch-party-type/", fetch_and_save_party_type, name="fetch_party_type"),
    path("api/get-party-types/", get_party_types_from_suffolk_api, name="get_party_types"),
    path("api/save-party-type/", save_party_type_to_session, name="save_party_type"),
    path("api/submit-final-filing/", submit_final_filing, name="submit_final_filing"),
    path("api/clear-session/", clear_session_data, name="clear_session_data"),
    path("api/debug-session/", debug_session_data, name="debug_session_data"),
    path("api/debug-session-data/", debug_session_data, name="debug_session_data"),
    # Jurisdiction management API
    path("api/jurisdiction/switch/", switch_jurisdiction, name="switch_jurisdiction"),
    path("api/jurisdiction/current/", get_current_jurisdiction, name="get_current_jurisdiction"),
    # API endpoints for upload functionality
    path("api/create-filing/", create_filing, name="create_filing"),
    path("api/simple-s3-upload/", simple_s3_upload, name="simple_s3_upload"),
    path("api/mock-s3-upload/", mock_s3_upload, name="mock_s3_upload"),
    path("api/test-s3-connection/", test_s3_connection, name="test_s3_connection"),
    # API endpoints for dropdowns
    path("api/", include("efile.api.urls")),
    # Legacy endpoints for backward compatibility (can be removed later)
    # path('api/get-case-categories/', views.efile_logout, name='get_case_categories_legacy'),
    # path('api/get-case-types/', views.efile_logout, name='get_case_types_legacy'),
    # path('api/get-filing-types/', views.efile_logout, name='get_filing_types_legacy'),
    # path('api/get-counties/', views.efile_logout, name='get_counties_legacy'),
    # path('api/get-document-types/', views.efile_logout, name='get_document_types_legacy'),
    # path('dashboard/', views.dashboard, name='dashboard'),
]
