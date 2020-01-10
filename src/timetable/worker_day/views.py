import datetime

from django_filters.rest_framework import FilterSet, BooleanFilter, NumberFilter, DjangoFilterBackend
from django_filters import utils
from rest_framework import filters
from rest_framework import serializers, viewsets, status, exceptions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from src.base.permissions import FilteredListPermission, Permission
from src.base.models import Employment, Shop
from src.timetable.models import WorkerDay

class MultiShopsFilterBackend(DjangoFilterBackend):
    """
    Чтобы составить расписание для магазина, надо получить расписание его сотрудников по всем другим магазинам
    Для этого получается список сотрудников магазина, список всех трудоустройств этих сотрудников,
    и расписание для всех трудоустройств
    """
    def filter_queryset(self, request, queryset, view):
        if view.detail:
            return super().filter_queryset(request, queryset, view)

        shop_id = request.query_params.get('shop_id')

        filterset = self.get_filterset(request,queryset,view)

        if filterset is None:
            return queryset

        if not filterset.is_valid() and self.raise_exception:
            raise utils.translate_validation(filterset.errors)

        form = filterset.form.cleaned_data

        dt = form.get('dt') #| request.data.get('dt')
        dt_from = form.get('dt_from')# | request.data.get('dt_from')
        dt_to = form.get('dt_to') #| request.data.get('dt_to')
        worker_id__in=form.get('worker_id__in')

        if not dt_from:
            dt_from = dt if dt else datetime.date.today()
        if not dt_to:
            dt_to = dt if dt else datetime.date.today()
        ids = Employment.objects.get_active(
            dt_from, dt_to,
            shop_id=shop_id,
        ).values('user_id')

        if worker_id__in:
            ids=ids.filter(
            user_id__in=worker_id__in
            )

        all_employments_for_users = Employment.objects.get_active(dt_from, dt_to).filter(user_id__in=ids)


        return super().filter_queryset(
            request, queryset, view
        ).filter(
            employment__in=all_employments_for_users)\
        .order_by('worker_id','dt','dttm_work_start')

# Serializers define the API representation.
class WorkerDaySerializer(serializers.ModelSerializer):
    # parent_id = serializers.IntegerField(required=False)
    class Meta:
        model = WorkerDay
        fields = ['id', 'worker', 'shop', 'employment', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'worker_day_approve_id']


class WorkerDayFilter(FilterSet):
    is_approved = BooleanFilter(field_name='worker_day_approve_id', method='filter_approved')


    def filter_approved(self, queryset, name, value):
        notnull = True
        if value:
            notnull = False

        # alternatively, it may not be necessary to construct the lookup.
        return queryset.filter(worker_day_approve_id__isnull=notnull)
    # shop_id = NumberFilter(required=True)


    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id':['exact'],
            'worker_id':['in','exact'],
            'dt': ['gte','lte','exact', 'range'],
            'is_approved': ['exact']
        }


class WorkerDayViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    permission_name = 'department'
    queryset = WorkerDay.objects.all()
    filter_backends = [MultiShopsFilterBackend]
    # filter_backends = [DjangoFilterBackend]

    def list(self, request,  *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


