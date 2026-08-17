"""
URL patterns for the API module
"""

from django.urls import path

from .auth_views import (
    external_profile,
    payment_account_types,
    payment_accounts,
    tyler_token,
    user_login,
    user_logout,
    user_profile,
)
from .case_type_config import get_case_type_config
from .config_views import get_filer_roles, get_form_config
from .dropdown_views import (
    get_case_categories,
    get_case_types,
    get_courts,
    get_document_types,
    get_filing_types,
    get_name_suffixes,
    get_optional_services,
    get_party_types,
)
from .filing_views import create_filing, delete_filing, get_filing_detail, get_filings, payment_fees, update_filing
from .s3_upload import (
    mock_s3_upload,
    simple_s3_upload,
    test_s3_connection,
)
from .suffolk_api_views import get_party_types_from_suffolk_api, lookup_case

app_name = "api"

urlpatterns = [
    path("get-party-types/", get_party_types_from_suffolk_api, name="get_party_types"),
    path("simple-s3-upload/", simple_s3_upload, name="simple_s3_upload"),
    path("mock-s3-upload/", mock_s3_upload, name="mock_s3_upload"),
    path("test-s3-connection/", test_s3_connection, name="test_s3_connection"),
    # path("api/create-filing/", create_filing, name="create_filing"),
    # Dropdown API endpoints
    path("dropdowns/case-categories/", get_case_categories, name="case_categories"),
    path("dropdowns/case-types/", get_case_types, name="case_types"),
    path("dropdowns/filing-types/", get_filing_types, name="filing_types"),
    path("dropdowns/courts/", get_courts, name="courts"),
    path("dropdowns/document-types/", get_document_types, name="document_types"),
    path("dropdowns/optional-services/", get_optional_services, name="optional_services"),
    path("dropdowns/party-types/", get_party_types, name="party_types"),
    path("dropdowns/name-suffixes/", get_name_suffixes, name="name_suffixes"),
    # Form configuration endpoints
    path("form-config/", get_form_config, name="form_config"),
    path("case-type-config/", get_case_type_config, name="case_type_config"),
    path("filer-roles/", get_filer_roles, name="filer_roles"),
    # Suffolk API endpoints
    path("suffolk/lookup-case/", lookup_case, name="lookup_case"),
    # Authentication API endpoints
    path("auth/login/", user_login, name="login"),
    path("auth/logout/", user_logout, name="logout"),
    path("auth/profile/", user_profile, name="profile"),
    path("auth/external-profile/", external_profile, name="external_profile"),
    path("auth/tyler-token/", tyler_token, name="tyler_token"),
    # Payment API endpoints
    path("payment-accounts/", payment_accounts, name="payment_accounts"),
    path("payment-account-types/", payment_account_types, name="payment_account_types"),
    path("payment-fees/", payment_fees, name="payment_fees"),
    # Filing API endpoints
    path("filings/", get_filings, name="get_filings"),
    path("filings/create/", create_filing, name="create_filing"),
    path("filings/<int:filing_id>/", get_filing_detail, name="filing_detail"),
    path("filings/<int:filing_id>/update/", update_filing, name="update_filing"),
    path("filings/<int:filing_id>/delete/", delete_filing, name="delete_filing"),
]
