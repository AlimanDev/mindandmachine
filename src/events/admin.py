from django.contrib import admin

from src.notifications.models import EventOnlineNotification, EventEmailNotification, EventWebhookNotification
from .models import EventType, EventHistory
from .registry import EventRegistryHolder


class EventOnlineNotificationInline(admin.StackedInline):
    model = EventOnlineNotification
    extra = 0
    filter_horizontal = ('users', 'shop_groups')


class EventEmailNotificationInline(admin.StackedInline):
    model = EventEmailNotification
    extra = 0
    filter_horizontal = ('users', 'shop_groups')


class EventWebhookNotificationInline(admin.StackedInline):
    model = EventWebhookNotification
    extra = 0


@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'write_history')

    inlines = (
        EventEmailNotificationInline,
        EventOnlineNotificationInline,
        EventWebhookNotificationInline,
    )

    def has_delete_permission(self, request, obj=None):
        has_perm = super(EventTypeAdmin, self).has_change_permission(request, obj=obj)
        if has_perm is False:
            return has_perm
        return getattr(obj, 'code', None) not in EventRegistryHolder.get_registry().keys()

    def has_change_permission(self, request, obj=None):
        has_perm = super(EventTypeAdmin, self).has_change_permission(request, obj=obj)
        if has_perm is False:
            return has_perm
        return getattr(obj, 'code', None) not in EventRegistryHolder.get_registry().keys()


@admin.register(EventHistory)
class EventHistoryAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'dttm_modified', 'shop', 'network', 'user_author', 'context')
    list_filter = ('network', 'event_type', 'shop', 'user_author')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
