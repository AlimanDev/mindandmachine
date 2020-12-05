import json

from django.http.response import Http404
from rest_framework import serializers, status
from rest_framework.response import Response

from src.base.exceptions import MessageError
from src.base.models import Shop
from src.base.permissions import FilteredListPermission
from src.base.views_abstract import GetObjectByCodeMixin, BaseModelViewSet
from src.forecast.models import Receipt


class PeriodClientsCreateSerializer(serializers.Serializer):
    data = serializers.JSONField(write_only=True)
    data_type = serializers.CharField(max_length=128, write_only=True)
    version = serializers.IntegerField(required=False)


# TODO: documentation
class ReceiptViewSet(GetObjectByCodeMixin, BaseModelViewSet):
    """
    """
    permission_classes = [FilteredListPermission]
    serializer_class = PeriodClientsCreateSerializer

    def get_queryset(self):
        return self.filter_queryset(Receipt.objects.all())

    @staticmethod
    def _get_receive_data_info(data_type, settings_values):
        for receive_data_info in settings_values['receive_data_info']:
            if receive_data_info['data_type'] == data_type:
                return receive_data_info

        raise MessageError(code='receive_data_info_not_found')

    def create(self, request, *args, **kwargs):
        serializer = PeriodClientsCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data['data']
        data_type = serializer.validated_data['data_type']
        settings_values = json.loads(self.request.user.network.settings_values)
        receive_data_info = self._get_receive_data_info(data_type, settings_values)

        for receipt in data:
            receipt[receive_data_info['shop_code_field_name']] = \
                receipt[receive_data_info['shop_code_field_name']].strip()

        receipt_codes = [receipt[receive_data_info['receipt_code_field_name']] for receipt in data]
        if Receipt.objects.filter(code__in=receipt_codes).exists():
            raise MessageError(code='multi_object_unique')

        shop_dict = {
            shop.code: shop.id for shop in
            Shop.objects.filter(
                network=self.request.user.network,
                code__in=[receipt[receive_data_info['shop_code_field_name']] for receipt in data],
            )
        }
        receipts = []
        for receipt in data:
            if shop_dict.get(receipt[receive_data_info['shop_code_field_name']], '') == '':
                raise MessageError(code='no_such_shop',
                                   params={'key': receipt[receive_data_info['shop_code_field_name']]})

            receipt = Receipt(
                shop_id=shop_dict[receipt[receive_data_info['shop_code_field_name']]],
                code=receipt[receive_data_info['receipt_code_field_name']],
                dttm=receipt[receive_data_info['dttm_field_name']],
                info=json.dumps(receipt),
                data_type=data_type,
            )
            if 'version' in serializer.validated_data:
                receipt.version = serializer.validated_data['version']
            receipts.append(receipt)
        Receipt.objects.bulk_create(receipts)

        return Response(status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        serializer = PeriodClientsCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data['data']
        data_type = serializer.validated_data['data_type']
        settings_values = json.loads(self.request.user.network.settings_values)
        receive_data_info = self._get_receive_data_info(data_type, settings_values)

        data[receive_data_info['shop_code_field_name']] = data[receive_data_info['shop_code_field_name']].strip()
        shop = Shop.objects.filter(code=data[receive_data_info['shop_code_field_name']]).first()
        if shop is None:
            raise MessageError(code='no_such_shop', params={'key': data[receive_data_info['shop_code_field_name']]})

        try:
            instance = self.get_object()
        except Http404:
            instance = Receipt()
        else:
            if 'version' in serializer.validated_data and instance.version > serializer.validated_data['version']:
                return Response({'detail': 'Versions mismatch'}, status=412)

        is_new = instance.pk is None

        instance.shop_id = shop.id
        instance.code = data[receive_data_info['receipt_code_field_name']]
        instance.dttm = data[receive_data_info['dttm_field_name']]
        instance.info = json.dumps(data)
        instance.data_type = data_type
        if 'version' in serializer.validated_data:
            instance.version = serializer.validated_data['version']
        instance.save()

        return Response(data, status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK)

# {
# "Ссылка": "954a22a1-cd84-11ea-8edf-00155d012a03",
# "Дата": "2020-07-24T11:06:32",
# "ТабельныйНомер": "НМЗН-03312",
# "ФИОПродавца": "Безносикова Светлана Павловна",
# "КодМагазина": "4001",
# "Guidзаказа": "00000000-0000-0000-0000-000000000000",
# "Номер": "RM-00501946",
# "ВидОперации": "Продажа",
# "ДисконтнаяКарта": "S03058    ",
# "ФизЛицо": "f0444dea-05da-11ea-8d9a-00155d01831d",
# "Магазин": "3669648",
# "ТипЗаказа": "Продажа салона",
# "КоличествоТоваровВЧеке": "1",
# "СуммаДокумента": "1323",
# "КодКупона": "",
# "Товары": [
# {
# "Нкод": "Ц0000000021",
# "Хкод": "Х0010319",
# "Количество": "1",
# "Цена": "1890",
# "СуммаБонус": "0",
# "СуммаСкидки": "567",
# "Сумма": "1323",
# "id": "1",
# "Скидки": [
# {
# "СкидкаНаценка": "Скидка сотруднику_НМ"
# }
# ],
# "КоличествоБонусов": "0",
# "ДатаНачисления": "0001-01-01T00:00:00",
# "ДатаСписания": "0001-01-01T00:00:00"
# }
# ]
# }
