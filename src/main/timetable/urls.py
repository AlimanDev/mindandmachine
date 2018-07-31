from django.urls import path, include
from .cashier import urls as cashier_urls
from .cashier_demand import urls as cashier_demand_urls
from .table import urls as table_urls
from .auto_settings import urls as auto_settings_urls
from .worker_exchange import urls as exchange_urls


urlpatterns = [
    path('cashier/', include(cashier_urls)),
    path('needs/', include(cashier_demand_urls)),
    path('table/', include(table_urls)),
    path('auto_settings/', include(auto_settings_urls)),
    path('worker_exchange/', include(exchange_urls))
]
