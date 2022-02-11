from django.urls import re_path
from src.misc.views import metabase_url


urlpatterns = [
    re_path('metabase_url/', metabase_url, name='rest_login'),
]
