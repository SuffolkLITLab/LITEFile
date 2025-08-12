from django.urls import path

from .views.login import efile_login
from .views.register import efile_register
from .views.options import efile_options
from . import views

urlpatterns = [
    path('login/', efile_login, name='efile_login'),
    path('register/', efile_register, name='efile_register'),
    path('options/', efile_options, name='efile_options'),
    # path('dashboard/', views.dashboard, name='dashboard'),
]