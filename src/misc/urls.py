from django.urls import re_path
from django.conf.urls import url
from django.conf import settings
from src.misc.views import metabase_url, protected_serve


urlpatterns = [
    re_path('metabase_url/', metabase_url, name='rest_login'),
    url(f'^{settings.MEDIA_PATH[1:]}(?P<path>.*)$', protected_serve, {'document_root': settings.MEDIA_ROOT}), # RegEx that catches /rest_api/media/*. Serves media for logged in users only.
]
