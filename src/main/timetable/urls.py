from django.urls import path, include
from .cashier import urls as cashier_urls

urlpatterns = [
    path('cashier/', include(cashier_urls)),
]
