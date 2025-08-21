from django.urls import path, include

from .views.register import efile_register
from .views.login import efile_login, efile_logout
from .views.options import efile_options
from .views.expert_form import efile_expert_form
from .views.upload import efile_upload, create_filing, upload_documents, test_s3_connection, simple_s3_upload, mock_s3_upload
from .views.review import case_review
from .views.confirmation import filing_confirmation
from .views.session_api import save_form_data_to_session, save_upload_data_to_session, get_upload_data_from_session, submit_final_filing, clear_session_data, debug_session_data
from .views.api_views import get_case_data
from . import views

urlpatterns = [
    path('login/', efile_login, name='efile_login'),
    path('logout/', efile_logout, name='efile_logout'),
    path('register/', efile_register, name='efile_register'),
    path('options/', efile_options, name='efile_options'),
    path('expert_form/', efile_expert_form, name='expert_form'),
    path('upload/', efile_upload, name='upload'),
    path('review/', case_review, name='case_review'),
    path('filing-confirmation/', filing_confirmation, name='filing_confirmation'),
    
    # Session API endpoints
    path('api/get-case-data/', get_case_data, name='get_case_data_from_session'),
    path('api/save-case-data/', save_form_data_to_session, name='save_form_data_to_session'),
    path('api/save-upload-data/', save_upload_data_to_session, name='save_upload_data_to_session'),
    path('api/get-upload-data/', get_upload_data_from_session, name='get_upload_data_from_session'),
    path('api/submit-final-filing/', submit_final_filing, name='submit_final_filing'),
    path('api/clear-session/', clear_session_data, name='clear_session_data'),
    path('api/debug-session/', debug_session_data, name='debug_session_data'),
    path('api/debug-session-data/', debug_session_data, name='debug_session_data'),
    
    # API endpoints for upload functionality
    path('api/create-filing/', create_filing, name='create_filing'),
    path('api/upload-documents/', upload_documents, name='upload_documents'),
    path('api/simple-s3-upload/', simple_s3_upload, name='simple_s3_upload'),
    path('api/mock-s3-upload/', mock_s3_upload, name='mock_s3_upload'),
    path('api/test-s3-connection/', test_s3_connection, name='test_s3_connection'),
    
    # API endpoints for dropdowns
    path('api/', include('efile.api.urls')),
    
    # Legacy endpoints for backward compatibility (can be removed later)
    # path('api/get-case-categories/', views.efile_logout, name='get_case_categories_legacy'),
    # path('api/get-case-types/', views.efile_logout, name='get_case_types_legacy'),
    # path('api/get-filing-types/', views.efile_logout, name='get_filing_types_legacy'),
    # path('api/get-counties/', views.efile_logout, name='get_counties_legacy'),
    # path('api/get-document-types/', views.efile_logout, name='get_document_types_legacy'),
    
    # path('dashboard/', views.dashboard, name='dashboard'),
]
