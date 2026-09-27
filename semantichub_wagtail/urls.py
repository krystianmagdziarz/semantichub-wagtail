from django.urls import path

from semantichub_wagtail.views import InboundArticleView, ManifestView

app_name = "semantichub_wagtail"

urlpatterns = [
    path("inbound/", InboundArticleView.as_view(), name="inbound"),
    path("manifest/", ManifestView.as_view(), name="manifest"),
]
