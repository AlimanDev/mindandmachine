from django.urls import re_path
from django.conf import settings
from src.adapters.metabase.views import metabase_url, protected_serve


urlpatterns = [
    re_path('metabase_url/', metabase_url, name='rest_login'),
    re_path(f'^{settings.MEDIA_PATH[1:]}(?P<path>.*)$', protected_serve, {'document_root': settings.MEDIA_ROOT}), # RegEx that catches /rest_api/media/*. Serves media for logged in users only.
]
