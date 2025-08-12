"""
URL patterns for the API module
"""
from django.urls import path
from .dropdown_views import (
    get_case_categories,
    get_case_types,
    get_filing_types,
    get_counties,
    get_document_types
)
from .auth_views import (
    user_login,
    user_logout,
    user_profile,
    external_auth
)
from .filing_views import (
    get_filings,
    create_filing,
    get_filing_detail,
    update_filing,
    delete_filing
)

app_name = 'api'

urlpatterns = [
    # Dropdown API endpoints
    path('dropdowns/case-categories/', get_case_categories, name='case_categories'),
    path('dropdowns/case-types/', get_case_types, name='case_types'),
    path('dropdowns/filing-types/', get_filing_types, name='filing_types'),
    path('dropdowns/counties/', get_counties, name='counties'),
    path('dropdowns/document-types/', get_document_types, name='document_types'),
    
    # Authentication API endpoints
    path('auth/login/', user_login, name='login'),
    path('auth/logout/', user_logout, name='logout'),
    path('auth/profile/', user_profile, name='profile'),
    path('auth/external/', external_auth, name='external_auth'),
    
    # Filing API endpoints
    path('filings/', get_filings, name='filings_list'),
    path('filings/create/', create_filing, name='create_filing'),
    path('filings/<int:filing_id>/', get_filing_detail, name='filing_detail'),
    path('filings/<int:filing_id>/update/', update_filing, name='update_filing'),
    path('filings/<int:filing_id>/delete/', delete_filing, name='delete_filing'),
]
