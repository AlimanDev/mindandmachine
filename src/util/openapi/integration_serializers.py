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
    class Meta:
        examples = {
            'code': '6F9619FF-8B86-D011-B42D-00CF4FC964FF',
            'name': 'Бабушкина',
            'address': 'Санкт-Петербург, ул. Бабушкина, 12/8',
            'parent_code': '7F9619FF-8B86-D011-B42D-00CF4FC964FF',
            'timezone': 'Europe/Moscow',
            'by_code': True,
            'tm_open_dict': {'d0': '10:00:00', 'd3': '11:00:00'},
            'tm_close_dict': {'d0': '20:00:00', 'd3': '21:00:00'},
            'latitude': '55.834244',
            'longitude': '37.513916',
        }
    code = serializers.CharField(help_text='Идентификатор подразделения (часто GUID из 1C)')
    name = serializers.CharField(help_text='Название подразделения (магазина)')
    address = serializers.CharField(help_text='Адрес')
    parent_code = serializers.CharField(required=False, help_text='Идентификатор подразделения родителя')
    timezone = TimeZoneField(required=False, help_text='Часовой пояс')
    by_code = serializers.BooleanField(help_text='Необходимо для синхронизации')
    tm_open_dict = serializers.JSONField(required=False, help_text='Словарь времени начала работы подразделений')
    tm_close_dict = serializers.JSONField(
        required=False, 
        help_text='''
        Словарь времени окончания работы подразделений Важно: если в словаре указываются дни, то они должны совпадать и в времени начала и в времени окоачания.''',
    )
    latitude = RoundingDecimalField(decimal_places=6, max_digits=12, allow_null=True, required=False, help_text='Широта (координаты подразделения)')
    longitude = RoundingDecimalField(decimal_places=6, max_digits=12, allow_null=True, required=False, help_text='Долгота (координаты подразделения)')
    email = serializers.EmailField(required=False, help_text='Почта (при наличии)')


class UserIntegrationSerializer(serializers.Serializer):
    class Meta:
        examples = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'middle_name': 'Иванович',
            'username': '1111',
            'by_code': True,
        }
    first_name = serializers.CharField(help_text='Имя')
    last_name = serializers.CharField(help_text='Фамилия')
    middle_name = serializers.CharField(required=False, help_text='Отчество')
    username = serializers.CharField(help_text='Логин (табельный номер)')
    email = serializers.EmailField(required=False, help_text='Почта (при наличии)')
    by_code = serializers.BooleanField(help_text='Необходимо для синхронизации')


class WorkerPositionIntegrationSerializer(serializers.Serializer):
    class Meta:
        examples = {
            'code': '1234',
            'name': 'Продавец',
            'by_code': True,
        }
    code = serializers.CharField(help_text='Внешний идентификатор')
    name = serializers.CharField(help_text='Название')
    by_code = serializers.BooleanField(help_text='Необходимо для синхронизации')


class EmploymentIntegrationSerializer(serializers.Serializer):
    class Meta:
        examples = {
            'dt_hired': '2019-07-17',
            'dt_fired': '2020-07-17',
            'username': '1111',
            'position_code': '1234',
            'shop_code': '6F9619FF-8B86-D011-B42D-00CF4FC964FF',
            'by_code': True,
        }
    dt_hired = serializers.DateField(help_text='Дата начала работы')
    dt_fired = serializers.DateField(help_text='Дата окончания работы')
    username = serializers.CharField(help_text='логин сотрудника')
    position_code = serializers.CharField(help_text='внешний идентификатор должности')
    shop_code = serializers.CharField(help_text='внешний идентификатор магазина')
    by_code = serializers.BooleanField(help_text='Необходимо для синхронизации')


class WorkerDayFilterIntegrationSerializer(serializers.Serializer):
    class Meta:
        examples = {
            'worker__username__in': '12345,123,345',
            'dt__gte': '2020-07-17',
            'dt__lte': '2019-07-17',
            'shop_code': '6F9619FF-8B86-D011-B42D-00CF4FC964FF',
            'hours_details': True,
            'is_tabel': True,
            'by_code': True,
        }
    worker__username__in = serializers.ListField(help_text='Список табельных сотрудников, по которым вернуть информацию по графику. Поле не обязательное, если указано shop_code', child=serializers.CharField())
    dt__gte = serializers.DateField(help_text='период выгрузки от даты (включительно)')
    dt__lte = serializers.DateField(help_text='период выгрузки до даты (включительно)')
    shop_code = serializers.CharField(help_text='Код магазина (если хотим по определенному магазину посмотреть график). Поле не обязательное, если есть worker__username__in')
    hours_details = serializers.BooleanField(help_text='Возвращать ли детали по часам работы (для табеля)')
    is_tabel = serializers.BooleanField(help_text='Получить данные для табеля. При этом добавлять is_approved и is_fact не нужно.')
    by_code = serializers.BooleanField(help_text='Возвращать ли данные по данным кодам синхронизации')


class ReceiptIntegrationSerializer(serializers.Serializer):
    class Meta:
        examples = {
            'data_type': 'bills',
            'data': {
                "shop_code": 1234,
                "dttm": "2020-07-20T11:00:00.000Z",
                "GUID": "…",
                "value": 2.3,
                "another_field": {},
            },
        }
    
    data_type = serializers.CharField(help_text='Тип события')
    data = serializers.JSONField(help_text='Информация по событию')
