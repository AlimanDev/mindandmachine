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
    list_filter = ('network',)

    inlines = (
        EventEmailNotificationInline,
        EventOnlineNotificationInline,
        EventWebhookNotificationInline,
    )

    def get_queryset(self, request):
        return super(EventTypeAdmin, self).get_queryset(request).filter(network_id=request.user.network_id)


@admin.register(EventHistory)
class EventHistoryAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'dttm_modified', 'shop', 'user_author', 'context')
    list_filter = ('event_type', 'shop', 'user_author')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super(EventHistoryAdmin, self).get_queryset(request).filter(
            event_type__network_id=request.user.network_id
        )
