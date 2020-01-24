from django.contrib import admin
from src.base.models import (
    Employment,
    User,
    Shop,
    Group,
    FunctionGroup,
    WorkerPosition,
    Region,
    ProductionDay
)

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')


@admin.register(WorkerPosition)
class WorkerPositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(User)
class QsUserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'shop_name', 'id')
    search_fields = ('first_name', 'last_name', 'id')
    # list_filter = ('employment__shop', )

    # list_display = ('first_name', 'last_name', 'employment__shop__title', 'parent_title', 'work_type_name', 'id')
    # search_fields = ('first_name', 'last_name', 'employment__shop__parent__title', 'workercashboxinfo__work_type__name', 'id')

    # @staticmethod
    # def parent_title(instance: User):
    #     if instance.shop and instance.shop.parent:
    #         return instance.shop.parent_title()
    #     return 'без магазина'

    @staticmethod
    def shop_name(instance: User):
        res = ', '.join(i.shop.name for i in instance.employments.all().select_related('shop'))
        return res
    '''
    @staticmethod
    def work_type_name(instance: User):
        cashboxinfo_set = instance.workercashboxinfo_set.all().select_related('work_type')
        return ' '.join(['"{}"'.format(cbi.work_type.name) for cbi in cashboxinfo_set])
    '''

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_title', 'id')
    search_fields = ('name', 'parent__name', 'id')

    @staticmethod
    def parent_title(instance: Shop):
        return instance.parent_title()


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_dispaly = ('id', 'dttm_added', 'name', 'subordinates')
    list_filter = ('id', 'name')


@admin.register(FunctionGroup)
class FunctionGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'access_type', 'group', 'func', 'method', 'level_down', 'level_up')
    list_filter = ('access_type', 'group', 'func')
    search_fields = ('id',)


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'user')
    list_filter = ('shop', 'user')
    search_fields = ('user__first_name', 'user__last_name', 'shop__name', 'shop__parent__name')


@admin.register(ProductionDay)
class ProductionDayAdmin(admin.ModelAdmin):
    list_display = ('dt', 'type')
