from django.contrib import admin

from .models import (
    EventEmailNotification,
    # EventOnlineNotification,
    # EventWebhookNotification,
    # SmtpServerSettings,
    # WebhookSettings,
)


class BaseEventNotificationAdmin(admin.ModelAdmin):
    pass


class BaseEventNotificationWithRecipientsAdmin(BaseEventNotificationAdmin):
    filter_horizontal = ('users', 'shop_groups')


@admin.register(EventEmailNotification)
class EventEmailNotificationAdmin(BaseEventNotificationWithRecipientsAdmin):
    pass


# @admin.register(EventOnlineNotification)
# class EventOnlineNotificationAdmin(BaseEventNotificationWithRecipientsAdmin):
#     pass


# @admin.register(EventWebhookNotification)
# class EventWebhookNotificationAdmin(BaseEventNotificationAdmin):
#     pass


# @admin.register(SmtpServerSettings)
# class SmtpServerSettingsAdmin(admin.ModelAdmin):
#     pass


# @admin.register(WebhookSettings)
# class WebhookSettingsAdmin(admin.ModelAdmin):
#     pass
