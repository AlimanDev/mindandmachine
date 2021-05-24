from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from django.http.response import Http404


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
        return super().get_object()


class BaseModelViewSet(ModelViewSet):
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
