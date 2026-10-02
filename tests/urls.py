from django.urls import include, path
from wagtail import urls as wagtail_urls

urlpatterns = [
    path("api/semantichub/", include("semantichub_wagtail.urls")),
    path("", include(wagtail_urls)),
]
