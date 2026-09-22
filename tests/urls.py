from django.urls import include, path

urlpatterns = [
    path("api/semantichub/", include("semantichub_wagtail.urls")),
]
