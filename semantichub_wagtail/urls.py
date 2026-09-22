from django.urls import path

from semantichub_wagtail.views import InboundArticleView, InboundPairView

app_name = "semantichub_wagtail"

urlpatterns = [
    path("inbound/", InboundArticleView.as_view(), name="inbound"),
    path("pair/", InboundPairView.as_view(), name="pair"),
]
