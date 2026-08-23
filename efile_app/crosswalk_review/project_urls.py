"""Root URL configuration for the standalone crosswalk review deployment."""

from django.urls import include, path

urlpatterns = [
    path("", include("crosswalk_review.urls")),
]
