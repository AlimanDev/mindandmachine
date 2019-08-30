from django.urls import path
from . import views

urlpatterns = [
    path('get_operation_templates', views.get_operation_templates),
    path('create_operation_template', views.create_operation_template),
    path('delete_operation_template', views.delete_operation_template),
    path('update_operation_template', views.update_operation_template),
]
