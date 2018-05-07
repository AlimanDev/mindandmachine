from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from src.db.models import (
    User,
    SuperShop,
    Shop,
    WorkerDay,
    PeriodDemand,
    PeriodDemandChangeLog,
    CashboxType,
    Cashbox,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    Notifications,
)



admin.site.register(User, UserAdmin)
admin.site.register(Shop)
admin.site.register(SuperShop)
admin.site.register(WorkerDay)
admin.site.register(PeriodDemand)
admin.site.register(PeriodDemandChangeLog)
admin.site.register(CashboxType)
admin.site.register(Cashbox)
admin.site.register(WorkerCashboxInfo)
admin.site.register(WorkerDayCashboxDetails)
admin.site.register(Notifications)