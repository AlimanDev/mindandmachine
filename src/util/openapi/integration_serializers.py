from rest_framework import serializers
import pytz
from src.util.drf.fields import RoundingDecimalField
from django.utils import six


class TimeZoneField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(pytz.common_timezones + [(None, "")], **kwargs)

    def to_representation(self, value):
        return str(six.text_type(super().to_representation(value)))


class ShopIntegrationSerializer(serializers.Serializer):
    code = serializers.CharField(help_text='Идентификатор подразделения (часто GUID из 1C)', default='6F9619FF-8B86-D011-B42D-00CF4FC964FF')
    name = serializers.CharField(help_text='Название подразделения (магазина)', default='Бабушкина')
    address = serializers.CharField(help_text='Адрес', default='Санкт-Петербург, ул. Бабушкина, 12/8')
    parent_code = serializers.CharField(required=False, help_text='Идентификатор подразделения родителя', default='7F9619FF-8B86-D011-B42D-00CF4FC964FF')
    timezone = TimeZoneField(required=False, help_text='Часовой пояс', default='Europe/Moscow')
    by_code = serializers.BooleanField(default=True, help_text='Необходимо для синхронизации')
    tm_open_dict = serializers.JSONField(required=False, help_text='Словарь времени начала работы подразделений', default={'d0': '10:00:00', 'd3': '11:00:00'})
    tm_close_dict = serializers.JSONField(
        required=False, 
        default={'d0': '20:00:00', 'd3': '21:00:00'},
        help_text='''
        Словарь времени окончания работы подразделений Важно: если в словаре указываются дни, то они должны совпадать и в времени начала и в времени окоачания.''',
    )
    latitude = RoundingDecimalField(decimal_places=6, max_digits=12, allow_null=True, required=False, default=55.834244, help_text='Широта (координаты подразделения)')
    longitude = RoundingDecimalField(decimal_places=6, max_digits=12, allow_null=True, required=False, default=37.513916, help_text='Долгота (координаты подразделения)')
    email = serializers.EmailField(required=False, help_text='Почта (при наличии)')


class UserIntegrationSerializer(serializers.Serializer):
    first_name = serializers.CharField(help_text='Имя', default='Иван')
    last_name = serializers.CharField(help_text='Фамилия', default='Иванов')
    middle_name = serializers.CharField(required=False, help_text='Отчество', default='Иванович')
    username = serializers.CharField(help_text='Логин (табельный номер)', default='1111')
    email = serializers.EmailField(required=False, help_text='Почта (при наличии)')
    by_code = serializers.BooleanField(default=True, help_text='Необходимо для синхронизации')
