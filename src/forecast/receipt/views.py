from src.base.permissions import FilteredListPermission
from src.base.exceptions import MessageError
from rest_framework import serializers, viewsets, status, exceptions, permissions
from rest_framework.response import Response

from src.forecast.models import Receipt
from src.base.models import Shop
import json


class PeriodClientsCreateSerializer(serializers.Serializer):
    data = serializers.JSONField(write_only=True)

# TODO: rewrite with check network
# TODO: documantation
class ReceiptViewSet(viewsets.ModelViewSet):
    """
    """
    permission_classes = [FilteredListPermission]

    def get_queryset(self):
        return self.filter_queryset(Receipt.objects.all())

    def get_object(self):
        if self.request.method == 'GET':
            by_code = self.request.query_params.get('by_code', False)
        else:
            by_code = self.request.data.get('by_code', False)
        if by_code:
            self.lookup_field = 'code'
            self.kwargs['code'] = self.kwargs['pk']
        return super().get_object()

    def create(self, request, *args, **kwargs):
        data = PeriodClientsCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data['data']

        shop_dict = {shop.code: shop.id for shop in Shop.objects.filter(code__in=[receipt['КодМагазина'] for receipt in data])}
        receipt_codes = [receipt['Ссылка'] for receipt in data]
        receipts = []
        for receipt in data:
            if shop_dict.get(receipt['КодМагазина'], '') == '':
                raise MessageError(code='no_such_shop', params={'key': receipt['КодМагазина']})

            receipts.append(Receipt(
                shop_id=shop_dict[receipt['КодМагазина']],
                code=receipt['Ссылка'],
                dttm=receipt['Дата'],
                info=json.dumps(receipt),
            ))
        if Receipt.objects.filter(code__in=receipt_codes).count():
            raise MessageError(code='multi_object_unique')

        Receipt.objects.bulk_create(receipts)
        return Response(status=status.HTTP_201_CREATED)


    def update(self, request, *args, **kwargs):
        data = PeriodClientsCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data['data']

        shop = Shop.objects.filter(code=data['КодМагазина']).first()
        if shop is None:
            raise MessageError(code='no_such_shop', params={'key': data['КодМагазина']})
        instance = self.get_object()
        instance.shop_id=shop.id
        instance.code=data['Ссылка']
        instance.dttm=data['Дата']
        instance.info=json.dumps(data)
        instance.save()

        return Response(data)


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
