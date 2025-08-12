from django.urls import path, include

from .views.login import efile_login
from .views.register import efile_register
from .views.options import efile_options
from .views.expert_form import efile_expert_form
from . import views

urlpatterns = [
    path('login/', efile_login, name='efile_login'),
    path('register/', efile_register, name='efile_register'),
    path('options/', efile_options, name='efile_options'),
    path('expert_form/', efile_expert_form, name='expert_form'),
    
    # API endpoints
    path('api/', include('efile.api.urls')),
    
    # Legacy endpoints for backward compatibility (can be removed later)
    # path('api/get-case-categories/', views.efile_logout, name='get_case_categories_legacy'),
    # path('api/get-case-types/', views.efile_logout, name='get_case_types_legacy'),
    # path('api/get-filing-types/', views.efile_logout, name='get_filing_types_legacy'),
    # path('api/get-counties/', views.efile_logout, name='get_counties_legacy'),
    # path('api/get-document-types/', views.efile_logout, name='get_document_types_legacy'),
    
    # path('dashboard/', views.dashboard, name='dashboard'),
]
