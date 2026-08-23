from django.urls import path

from . import views

app_name = "crosswalk_review"

urlpatterns = [
    path("", views.index, name="index"),
    path("form/<str:canonical_id>/", views.review_form, name="review_form"),
    path("next/", views.next_unreviewed, name="next_unreviewed"),
    path("progress/", views.progress, name="progress"),
    path("export.csv", views.export_csv, name="export_csv"),
]
