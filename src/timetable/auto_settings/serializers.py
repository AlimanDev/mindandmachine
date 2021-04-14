from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class BaseAutoSettingsSerializer(serializers.Serializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
    }

    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)

        if self.validated_data.get('dt_from') > self.validated_data.get('dt_to'):
            raise self.fail('check_dates')


class AutoSettingsCreateSerializer(BaseAutoSettingsSerializer):
    is_remaking = serializers.BooleanField(default=False, help_text='Пересоставление')
    use_not_approved = serializers.BooleanField(default=False, help_text='Использовать неподтвержденную версию')


class AutoSettingsDeleteSerializer(BaseAutoSettingsSerializer):
    delete_created_by = serializers.BooleanField(default=False, help_text='Удалить ручные изменения')


class AutoSettingsSetSerializer(serializers.Serializer):
    data = serializers.JSONField(help_text='Данные в формате JSON от сервера.')
