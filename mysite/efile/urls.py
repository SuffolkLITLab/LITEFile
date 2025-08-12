from django.urls import path

from .views.login import efile_login
from .views.register import efile_register

urlpatterns = [
    path("login/", efile_login, name="efile_login"),
    path("register/", efile_register, name="efile_register"),
    # path('dashboard/', views.dashboard, name='dashboard'),
]
