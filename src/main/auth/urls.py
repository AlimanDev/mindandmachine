from django.urls import path
from . import views
from django.conf.urls import url

from src.base.auth.views import WFMTokenLoginView

urlpatterns = [
    path('update_csrf', views.update_csrf),
    path('signin', views.signin),
    path('signout', views.signout),
    path('is_signed', views.is_signed),
    path('rotate_fcm_token', views.rotate_fcm_token),

    url('signin_token', WFMTokenLoginView.as_view(), kwargs={'version': '0.9'}),  # deprecated использует MD AUDIT сейчас
]
