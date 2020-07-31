from rest_framework import serializers, viewsets, exceptions, permissions

from django_filters.rest_framework import FilterSet
from django_filters import NumberFilter

from src.base.permissions import Permission
from src.forecast.models import Receipt
from src.base.models import Shop


class ReceiptSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(required=False)
    code = serializers.UUIDField(required=False)
    dttm = serializers.DateField(required=False)
    info = serializers.JSONField()

    class Meta:
        model = Receipt
        fields = [
            'id', 'code', 'dttm', 'dttm_added', 'dttm_modified', 'shop_id', 'info',
        ]
        read_only_fields = ['dttm_added', 'dttm_modified']

    def create(self, validated_data):
        info = validated_data['info']
        try:
            shop = Shop.objects.get(code=info['КодМагазина'])
        except Shop.DoesNotExist:
            raise exceptions.ValidationError(f"department with id {info['КодМагазина']} does not exist")
        validated_data['shop_id'] = shop.id
        validated_data['code'] = info['Ссылка']
        validated_data['dttm'] = info['Дата']
        return Receipt.objects.create(**validated_data)
    def update(self, instance, validated_data):
        info = validated_data['info']
        instance.dttm = info['Дата']
        instance.save()




class ReceiptFilter(FilterSet):
    shop_id = NumberFilter()

    class Meta:
        model = Receipt
        fields=['shop_id']

 
class ReceiptViewSet(viewsets.ModelViewSet):
    queryset = Receipt.objects.all()
    permission_classes = [permissions.IsAdminUser]
    filterset_class = ReceiptFilter
    serializer_class = ReceiptSerializer

    def perform_update(self, serializer):
        info = serializer.info
        serializer.dttm = info['Дата']
        serializer.save()

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
