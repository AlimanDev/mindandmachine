from django.contrib import admin

from src.notifications.models import (
    EventEmailNotification,
    # EventOnlineNotification,
    # EventWebhookNotification,
)
from .models import EventType, EventHistory
# from .registry import EventRegistryHolder


# class EventOnlineNotificationInline(admin.StackedInline):
#     model = EventOnlineNotification
#     extra = 0
#     filter_horizontal = ('users', 'shop_groups')


class EventEmailNotificationInline(admin.StackedInline):
    model = EventEmailNotification
    extra = 0
    filter_horizontal = ('users', 'shop_groups')


# class EventWebhookNotificationInline(admin.StackedInline):
#     model = EventWebhookNotification
#     extra = 0


@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'write_history', 'network')
    list_filter = ('network',)
    search_fields = ('name', 'code', 'network')
    list_select_related = ('network',)

    inlines = (
        EventEmailNotificationInline,
        # EventOnlineNotificationInline,
        # EventWebhookNotificationInline,
    )


@admin.register(EventHistory)
class EventHistoryAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'dttm_modified', 'shop', 'user_author', 'context')
    list_filter = ('event_type__network', 'event_type', 'shop', 'user_author')
    list_select_related = ('event_type__network', 'shop', 'user_author')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
