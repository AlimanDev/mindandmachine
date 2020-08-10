from django.conf.urls import url
from src.misc.views import metabase_url


urlpatterns = [
    url('metabase_url/', metabase_url, name='rest_login'),
]
