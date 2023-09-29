from django.http.response import Http404
from django.db.models import F, Manager
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from src.common.drf.exceptions import NotImplementedAPIException
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
        model_options = options.get('model_options', {})
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
            check_perms_extra_kwargs=dict(
                grouped_checks=model_options.pop('grouped_checks', False),
                check_active_empl=model_options.pop('check_active_empl', True),
            ),
            model_options=model_options,
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
    available_extra_fields = []
    def _get_available_extra_fields(self, request):
        if request is None:
            return []
        extra_fields = request.query_params.get('extra_fields') or request.data.get('extra_fields') or []
        if extra_fields:
            extra_fields = set(map(lambda x: x.strip(), extra_fields.split(',')))
        available_extra_fields = set(self.available_extra_fields).intersection(extra_fields)
        return list(available_extra_fields)

    def get_manager(self):
        model = self.queryset.model
        manager = model.objects
        if self.action in ['update'] and hasattr(model, 'objects_with_excluded'):
            manager = model.objects_with_excluded
        
        return manager

    def get_queryset(self):
        manager: Manager = self.get_manager()
        if getattr(self, 'swagger_fake_view', False):   # for schema generation metadata
            return manager.none()
        available_extra_fields = self._get_available_extra_fields(self.request)

        return manager.annotate(
            **{
                extra_field: F(extra_field) for extra_field in available_extra_fields
            }
        )

    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):   # for schema generation metadata
            return serializers.Serializer
        return super().get_serializer_class()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['extra_fields'] = self._get_available_extra_fields(self.request)
        return context


class BaseActiveNamedModelViewSet(GetObjectByCodeMixin, BaseModelViewSet):
    """
    Класс переопределяющий get_object() для возможности
    получения сущности по коду либо иному полю, указанному
    в свойстве get_object_field
    """


class UpdateorCreateViewSet(BaseActiveNamedModelViewSet):
    """
    аа: для упрощения интеграции клиентам удобнее обновлять или создавать модель одним и тем же запросом.
    Данный класс переопределяет update по такой логике, чтобы:
    вначале попытаться обновить сущность, а потом ее создать.

    """

    def update(self, request, *args, **kwargs):
        try:
            return super(UpdateorCreateViewSet, self).update(request, *args, **kwargs)
        except Http404:
            return self.create(request, *args, **kwargs)
