from django.urls import re_path

from .views import GetEmbedInfoAPIView

urlpatterns = [
    re_path(r'^get_embed_info/$', GetEmbedInfoAPIView.as_view(), name='get_embed_info'),
]
