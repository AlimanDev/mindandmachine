from django.conf.urls import url

from .views import GetEmbedInfoAPIView

urlpatterns = [
    url(r'^get_embed_info/$', GetEmbedInfoAPIView.as_view(), name='get_embed_info'),
]
