from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from django.http.response import Http404


class BaseActiveNamedModelViewSet(ModelViewSet):
    '''
    Класс переопределяющий get_object() для возможности
    получения сущности по коду либо иному полю, указанному
    в свойстве get_object_field
    '''
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


class UpdateorCreateViewSet(BaseActiveNamedModelViewSet):
    """
    аа: для упращения интеграции клиентам удобнее обновлять или создавать модель одним и тем же запросом.
    Данный класс переопределяет update по такой логике, чтобы:
    вначале попытаться обновить сущность, а потом ее создать.

    """

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)

        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            if getattr(instance, '_prefetched_objects_cache', None):
                # If 'prefetch_related' has been applied to a queryset, we need to
                # forcibly invalidate the prefetch cache on the instance.
                instance._prefetched_objects_cache = {}

            return Response(serializer.data)
        except Http404:
            return self.create(request, *args, **kwargs)