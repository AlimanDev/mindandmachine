from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from src.base.models import (
    Shop,
    Employee,
)
from src.forecast.models import (
    OperationType,
    OperationTypeName,

)
from src.forecast.operation_type.views import OperationTypeSerializer
from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "no_shop": _("There is {amount} models of shop with code: {code}."),
        "no_operation_type_name": _("There is {amount} models of shop with code: {code}."),
        "no_employee": _("There is {amount} models of shop with tabel_code: {tabel_code}."),
    }

    operation_type = OperationTypeSerializer(read_only=True)
    operation_type_id = serializers.IntegerField(write_only=True, required=False)
    operation_type_code = serializers.CharField(write_only=True, required=False)
    shop_code = serializers.CharField(write_only=True, required=False)
    employee_id = serializers.IntegerField(required=False)
    tabel_code = serializers.CharField(required=False)

    class Meta:
        model = Task
        fields = (
            'id',
            'code',
            'dt',
            'dttm_start_time',
            'dttm_end_time',
            'operation_type',
            'operation_type_id',
            'operation_type_code',
            'shop_code',
            'employee_id',
            'tabel_code',
            'dttm_event',
        )
        extra_kwargs = {
            'dt': {
                'required': False,
            },
            'dttm_event': {
                'write_only': True,
            },
        }

    def validate(self, attrs):
        if (attrs.get('operation_type_id') is None) and ('shop_code' in attrs and 'operation_type_code' in attrs):
            shop_code = attrs.pop('shop_code')
            operation_type_name_code = attrs.pop('operation_type_code')
            operation_type = OperationType.objects.filter(
                shop__code=shop_code,
                operation_type_name__code=operation_type_name_code,
            ).first()
            if operation_type:
                attrs['operation_type_id'] = operation_type.id
            else:
                operation_type_names = list(OperationTypeName.objects.filter(code=operation_type_name_code))
                if len(operation_type_names) != 1:
                    self.fail('no_operation_type_name', amount=len(operation_type_names), code=operation_type_name_code)

                shops = list(Shop.objects.filter(code=shop_code))
                if len(shops) != 1:
                    self.fail('no_shop', amount=len(operation_type_names), code=operation_type_name_code)

                operation_type_name = operation_type_names[0]
                shop = shops[0]
                operation_type = OperationType.objects.create(
                    shop=shop,
                    operation_type_name=operation_type_name,
                )
                attrs['operation_type_id'] = operation_type.id

        if (attrs.get('employee_id') is None) and ('tabel_code' in attrs):
            tabel_code = attrs.pop('tabel_code')
            employees = list(Employee.objects.filter(
                tabel_code=tabel_code, user__network_id=self.context['request'].user.network_id))
            if len(employees) == 1:
                attrs['employee_id'] = employees[0].id
            else:
                self.fail('no_employee', amount=len(employees), tabel_code=tabel_code)

        return attrs
