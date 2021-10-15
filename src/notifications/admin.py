from django.contrib import admin
from src.base.admin import BaseNotWrapRelatedModelaAdmin

from src.notifications.forms import EventEmailNotificationForm

from .models import (
    EventEmailNotification,
    # EventOnlineNotification,
    # EventWebhookNotification,
    # SmtpServerSettings,
    # WebhookSettings,
)


class BaseEventNotificationAdmin(BaseNotWrapRelatedModelaAdmin):
    pass


class BaseEventNotificationWithRecipientsAdmin(BaseEventNotificationAdmin):
    filter_horizontal = ('users', 'shop_groups')


@admin.register(EventEmailNotification)
class EventEmailNotificationAdmin(BaseEventNotificationWithRecipientsAdmin):
    form = EventEmailNotificationForm
    not_wrap_fields = ['event_type']


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
