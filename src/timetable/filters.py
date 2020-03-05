import datetime

from django_filters.rest_framework import FilterSet, BooleanFilter, DjangoFilterBackend, NumberFilter
from django_filters import utils

from src.base.models import Employment
from src.timetable.models import WorkerDay, WorkerDayApprove


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


class WorkerDayApproveFilter(FilterSet):
    class Meta:
        model = WorkerDayApprove
        fields = {
            'shop_id':['exact'],
            'created_by':['exact'],
            'dt_approved': ['gte','lte'],
            'dttm_added': ['gte','lte'],
        }


class WorkerDayFilter(FilterSet):
    is_approved = BooleanFilter(field_name='worker_day_approve_id', method='filter_approved')

    def filter_approved(self, queryset, name, value):
        notnull = True
        if value:
            notnull = False

        return queryset.filter(worker_day_approve_id__isnull=notnull)


    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id':['exact'],
            'worker_id':['in','exact'],
            'dt': ['gte','lte','exact', 'range'],
            'is_approved': ['exact']
        }

