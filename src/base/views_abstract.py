from django.http.response import Http404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from src.util.drf.exceptions import NotImplementedAPIException
from .mixins import GetObjectByCodeMixin, ApiLogMixin


class BatchUpdateOrCreateOptionsSerializer(serializers.Serializer):
    by_code = serializers.BooleanField(required=False)
    update_key_field = serializers.CharField(required=False)
    delete_scope_fields_list = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True, allow_null=False)
    delete_scope_values_list = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=False, allow_null=False)
    delete_scope_filters = serializers.DictField(required=False)
    rel_objs_delete_scope_filters = serializers.DictField(required=False)
    return_response = serializers.BooleanField(required=False, allow_null=False)
    grouped_checks = serializers.BooleanField(required=False, allow_null=False)
    dry_run = serializers.BooleanField(required=False)
    diff_report_email_to = serializers.ListField(child=serializers.CharField(), required=False)
    model_options = serializers.DictField(required=False)


def _patch_obj_serializer(obj_serializer, update_key_field='id'):
    obj_serializer.child.fields[update_key_field].read_only = False
    obj_serializer.child.fields[update_key_field].required = False
    obj_serializer.child.fields[update_key_field].allow_null = True


class BatchUpdateOrCreateViewMixin:
    batch_update_or_create_serializer_cls = None

    def get_batch_update_or_create_serializer_cls(self):
        obj_serializer_сls = self.batch_update_or_create_serializer_cls or self.serializer_class
        this = self

        class BatchUpdateOrCreateSerializer(serializers.Serializer):
            data = obj_serializer_сls(many=True)
            options = BatchUpdateOrCreateOptionsSerializer(required=False)

            def __init__(self, *args, **kwargs):
                super(BatchUpdateOrCreateSerializer, self).__init__(*args, **kwargs)
                update_key_field = this.request.data.get('options', {}).get('update_key_field')
                by_code = this.request.data.get('options', {}).get('by_code')
                _patch_obj_serializer(
                    obj_serializer=self.fields['data'],
                    update_key_field=update_key_field or ('code' if by_code else 'id')
                )

        return BatchUpdateOrCreateSerializer

    def get_batch_update_or_create_serializer(self, *args, **kwargs):
        batch_update_or_create_serializer_cls = self.get_batch_update_or_create_serializer_cls()
        kwargs['context'] = self.get_serializer_context()
        kwargs['context']['batch'] = True
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

        options = serializer.validated_data.get('options', {})
        delete_scope_filters = options.get('delete_scope_filters', {})
        if options.get('by_code'):
            delete_scope_filters.update({'code__isnull': False})
        objects, stats = self._get_model_from_serializer(serializer).batch_update_or_create(
            data=serializer.validated_data.get('data'),
            update_key_field=options.get('update_key_field') or ('code' if options.get('by_code') else 'id'),
            delete_scope_fields_list=options.get('delete_scope_fields_list'),
            delete_scope_values_list=options.get('delete_scope_values_list'),
            delete_scope_filters=delete_scope_filters,
            rel_objs_delete_scope_filters=options.get('rel_objs_delete_scope_filters', {}),
            user=self.request.user if self.request.user.is_authenticated else None,
            dry_run=options.get('dry_run', False),
            diff_report_email_to=options.get('diff_report_email_to'),
            model_options=options.get('model_options', {}),
            check_perms_extra_kwargs=dict(
                grouped_checks=options.get('grouped_checks', False),
            ),
        )

        res = {
            'stats': stats,
        }
        if options.get('return_response', False):  # для перерендеринга на фронте
            res['data'] = self.get_batch_update_or_create_serializer(
                instance={
                    'data': objects,
                },
            ).data['data']
        return Response(res)


class BaseModelViewSet(ApiLogMixin, BatchUpdateOrCreateViewMixin, ModelViewSet):
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
