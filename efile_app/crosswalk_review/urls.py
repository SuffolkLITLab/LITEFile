from django.urls import path

from . import views

app_name = "crosswalk_review"

urlpatterns = [
    path("", views.index, name="index"),
    path("form/<str:canonical_id>/", views.review_form, name="review_form"),
    path("pdf/<str:canonical_id>/", views.local_form_pdf, name="local_form_pdf"),
    path("next/", views.next_unreviewed, name="next_unreviewed"),
    path("progress/", views.progress, name="progress"),
    path("api/taxonomy/<str:level>/", views.taxonomy_options, name="taxonomy_options"),
    path("export.csv", views.export_csv, name="export_csv"),
    path("export.json", views.export_json, name="export_json"),
]
