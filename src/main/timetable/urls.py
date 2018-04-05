from django.urls import path, include
from .cashier import urls as cashier_urls
from .cashier_demand import urls as cashier_demand_urls


urlpatterns = [
    path('cashier/', include(cashier_urls)),
    path('needs/', include(cashier_demand_urls))
]
