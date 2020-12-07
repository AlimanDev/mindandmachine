from rest_framework import serializers

from src.events.registry import BaseRegisteredEvent

REQUEST_APPROVE_EVENT_TYPE = 'request_approve'
APPROVE_EVENT_TYPE = 'approve'


class RequestApproveEventSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    grouped_worker_dates = serializers.DictField(child=serializers.ListSerializer(child=serializers.DateField()))


class RequestApproveEvent(BaseRegisteredEvent):
    name = 'Запрос на подтверждение графика'
    code = REQUEST_APPROVE_EVENT_TYPE


class ApproveEvent(BaseRegisteredEvent):
    name = 'Подтверждение графика'
    code = APPROVE_EVENT_TYPE
    context_serializer_cls = RequestApproveEventSerializer
