from django.urls import path
from . import views


urlpatterns = [
    # path('update_csrf', views.update_csrf),
    path('signin', views.signin),
    path('signout', views.signout),
]
