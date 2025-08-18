from django.urls import path, include

from .views.register import efile_register
from .views.login import efile_login
from .views.options import efile_options
from .views.expert_form import efile_expert_form
from .views.upload import efile_upload, create_filing, upload_documents, test_s3_connection
from .views.review import case_review
from .views.session_api import save_form_data_to_session
from . import views

urlpatterns = [
    path('login/', efile_login, name='efile_login'),
    path('register/', efile_register, name='efile_register'),
    path('options/', efile_options, name='efile_options'),
    path('expert_form/', efile_expert_form, name='expert_form'),
    path('upload/', efile_upload, name='upload'),
    path('review/', case_review, name='case_review'),
    
    # API endpoints for form data
    path('api/save-form-data/', save_form_data_to_session, name='save_form_data'),
    
    # API endpoints for upload functionality
    path('api/create-filing/', create_filing, name='create_filing'),
    path('api/upload-documents/', upload_documents, name='upload_documents'),
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
