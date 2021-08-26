from django.http.response import Http404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from src.util.drf.exceptions import NotImplementedAPIException


class GetObjectByCodeMixin:
    get_object_field = 'code'

    def get_object(self):
        if self.request.method == 'GET':
            by_code = self.request.query_params.get('by_code', False)
        else:
            by_code = self.request.data.get('by_code', False)
        if by_code:
            self.lookup_field = self.get_object_field
            self.kwargs[self.get_object_field] = self.kwargs['pk']
        self.request.by_code = by_code
        return super().get_object()


class BatchUpdateOrCreateOptionsSerializer(serializers.Serializer):
    update_key_field = serializers.CharField(required=False, allow_blank=False, allow_null=False)
    delete_scope_fields_list = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=False, allow_null=False)
    delete_scope_values_list = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=False, allow_null=False)
    return_response = serializers.BooleanField(required=False, allow_null=False)


def _patch_obj_serializer(obj_serializer, update_key_field=None):
    update_key_field = update_key_field or 'id'
    obj_serializer.child.fields[update_key_field].read_only = False
    obj_serializer.child.fields[update_key_field].required = False
    obj_serializer.child.fields[update_key_field].allow_null = True
    if 'dttm_modified' not in obj_serializer.child.fields:
        obj_serializer.child.fields['dttm_modified'] = serializers.DateTimeField(read_only=True)


class BatchUpdateOrCreateMixin:
    batch_update_or_create_serializer_cls = None

    def get_batch_update_or_create_serializer_cls(self):
        obj_serializer_сls = self.batch_update_or_create_serializer_cls or self.serializer_class
        this = self

        class BatchUpdateOrCreateSerializer(serializers.Serializer):
            data = obj_serializer_сls(many=True)
            options = BatchUpdateOrCreateOptionsSerializer(required=False)

            def __init__(self, *args, **kwargs):
                super(BatchUpdateOrCreateSerializer, self).__init__(*args, **kwargs)
                _patch_obj_serializer(
                    obj_serializer=self.fields['data'],
                    update_key_field=this.request.data.get('options', {}).get('update_key_field', None)
                )

        return BatchUpdateOrCreateSerializer

    def get_batch_update_or_create_serializer(self, *args, **kwargs):
        batch_update_or_create_serializer_cls = self.get_batch_update_or_create_serializer_cls()
        kwargs['context'] = self.get_serializer_context()
        return batch_update_or_create_serializer_cls(*args, **kwargs)

    def _get_model_from_serializer(self, serializer):
        try:
            return serializer.fields['data'].child.Meta.model
        except Exception as e:
            # TODO: запись в лог?
            raise NotImplementedAPIException()

    @action(detail=False, methods=['post', 'put'])
    def batch_update_or_create(self, request):
        serializer = self.get_batch_update_or_create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return_response = serializer.validated_data.get('options', {}).pop('return_response', False)

        objects, stats = self._get_model_from_serializer(serializer).batch_update_or_create(
            data=serializer.validated_data.get('data'),
            user=self.request.user if self.request.user.is_authenticated else None,
            **serializer.validated_data.get('options', {}),
        )

        res = {
            'stats': stats,
        }
        if return_response:  # скорее всего нужно для перерендеринга на фронте
            res['data'] = self.get_batch_update_or_create_serializer(
                instance={
                    'data': objects,
                },
            ).data['data']
        return Response(res)


class BaseModelViewSet(BatchUpdateOrCreateMixin, ModelViewSet):
    http_method_names = ['get', 'post', 'put', 'delete']


class BaseActiveNamedModelViewSet(GetObjectByCodeMixin, BaseModelViewSet):
    """
    Класс переопределяющий get_object() для возможности
    получения сущности по коду либо иному полю, указанному
    в свойстве get_object_field
    """


class UpdateorCreateViewSet(BaseActiveNamedModelViewSet):
    """
    аа: для упращения интеграции клиентам удобнее обновлять или создавать модель одним и тем же запросом.
    Данный класс переопределяет update по такой логике, чтобы:
    вначале попытаться обновить сущность, а потом ее создать.

    """

    def update(self, request, *args, **kwargs):
        try:
            return super(UpdateorCreateViewSet, self).update(request, *args, **kwargs)
        except Http404:
            return self.create(request, *args, **kwargs)
