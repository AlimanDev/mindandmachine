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

    # def get_queryset(self):
    #     user = self.request.user
    #             # Response({"error": "shop_id not found."},
    #             #      status=status.HTTP_404_NOT_FOUND)
    #     dt = self.request.query_params.get('dt') #| request.data.get('dt')
    #     dt_from = self.request.query_params.get('dt_from')# | request.data.get('dt_from')
    #     dt_to = self.request.query_params.get('dt_to') #| request.data.get('dt_to')
    #     shop_id = self.request.query_params.get('shop_id')# | request.data.get('shop_id')
    #     worker_id__in=self.request.query_params.get('worker_id__in')
    #
    #     if not dt_from:
    #         dt_from = dt if dt else datetime.date.today()
    #     if not dt_to:
    #         dt_to = dt if dt else datetime.date.today()
    #     employments = Employment.objects.get_active(
    #         dt_from, dt_to,
    #         shop_id=shop_id,
    #     )
    #
    #     if worker_id__in:
    #         employments=employments.filter(
    #         user_id__in=worker_id__in
    #         )
    #
    #     queryset = super().get_queryset()
    #     queryset = queryset.filter(employment__in=employments)
    #


        # return WorkerDay.objects.filter(shop_id=shop_id)

    def list(self, request,  *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # def get_permissions(self):
    #     if self.action=='list':
    #         return [FilteredListPermission()]
    #     else:
    #         return [Permission()]

    # @action(detail=False, methods=['get']) #, permission_classes=[IsAdminOrIsSelf])
    # def timetable(self, request):
    #     """
    #     Возвращает информацию о расписании сотрудника
    #
    #     Args:
    #         method: GET
    #         url: /api/timetable/cashier/get_cashier_timetable
    #         worker_ids(list): required = True
    #         from_dt(QOS_DATE): с какого числа смотреть расписание
    #         to_dt(QOS_DATE): по какое число
    #         shop_id(int): required = True
    #         approved_only: required = False, только подтвержденные
    #         checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)
    #
    #     Returns:
    #         {
    #             'user': { в формате как get_cashiers_list },\n
    #             'indicators': {
    #                 | 'change_amount': количество измененных дней,
    #                 | 'holiday_amount': количество выходных,
    #                 | 'sick_day_amount': количество больничных,
    #                 | 'vacation_day_amount': количество отпускных дней,
    #                 | 'work_day_amount': количество рабочих дней,
    #                 | 'work_day_in_holidays_amount': количество рабочих дней в выходные
    #             },\n
    #             'days': [
    #                 {
    #                     'day': {
    #                         | 'id': id worker_day'a,
    #                         | 'dttm_added': дата добавления worker_day'a,
    #                         | 'dt': worker_day dt,
    #                         | 'worker': id пользователя,
    #                         | 'type': тип worker_day'a,
    #                         | 'dttm_work_start': дата-время начала работы,
    #                         | 'dttm_work_end': дата-время конца рабочего дня,
    #                         | 'work_types': [список id'шников типов касс, на которых сотрудник работает в этот день],
    #                     },\n
    #                     | 'change_requests': [список change_request'ов],
    #                 }
    #             ]
    #         }
    #
    #     """
    #     shop = Shop.objects.get(id=form['shop_id'])
    #     from_dt = form['from_dt']
    #     to_dt = form['to_dt']
    #     checkpoint = FormUtil.get_checkpoint(form)
    #     approved_only = form['approved_only']
    #     work_types = {w.id: w for w in WorkType.objects.select_related('shop').all()}
    #
    #     def check_wd(wd):
    #         work_type = wd.work_types.first()
    #         if work_type and work_type.shop_id != form['shop_id']:
    #             wd.other_shop = work_type.shop.title
    #         return wd
    #
    #     response = {}
    #     # todo: rewrite with 1 request instead 80
    #     for worker_id in form['worker_ids']:
    #         try:
    #             employment = Employment.objects.get(user_id=worker_id, shop_id=form['shop_id'])
    #         except ObjectDoesNotExist:
    #             continue
    #
    #         worker_days_filter = WorkerDay.objects.qos_filter_version(checkpoint).select_related(
    #             'employment').prefetch_related('work_types').filter(
    #             Q(employment__dt_fired__gt=from_dt) &
    #             Q(dt__lt=F('employment__dt_fired')) |
    #             Q(employment__dt_fired__isnull=True),
    #
    #             Q(employment__dt_hired__lte=to_dt) &
    #             Q(dt__gte=F('employment__dt_hired')) |
    #             Q(employment__dt_hired__isnull=True),
    #
    #             employment__user_id=worker_id,
    #             employment__shop_id=form['shop_id'],
    #             dt__gte=from_dt,
    #             dt__lte=to_dt,
    #         ).order_by(
    #             'dt'
    #         )
    #         worker_days = list(worker_days_filter)
    #
    #         official_holidays = [
    #             x.dt for x in ProductionDay.objects.filter(
    #                 dt__gte=from_dt,
    #                 dt__lte=to_dt,
    #                 type=ProductionDay.TYPE_HOLIDAY,
    #                 region_id=shop.region_id,
    #             )
    #         ]
    #
    #         wd_logs = WorkerDay.objects.select_related('employment').filter(
    #             Q(created_by__isnull=False),
    #             # Q(parent_worker_day__isnull=False) | Q(created_by__isnull=False),
    #             worker_id=worker_id,
    #             dt__gte=from_dt,
    #             dt__lte=to_dt,
    #         )
    #
    #         if approved_only:
    #             wd_logs = wd_logs.filter(
    #                 worker_day_approve_id__isnull=False
    #             )
    #         worker_day_change_log = {}
    #         for wd_log in list(wd_logs.order_by('-id')):
    #             key = WorkerDay.objects.qos_get_current_worker_day(wd_log).id
    #             if key not in worker_day_change_log:
    #                 worker_day_change_log[key] = []
    #             worker_day_change_log[key].append(wd_log)
    #         '''
    #
    #         wd_logs = list(wd_logs)
    #         worker_day_change_log = group_by(
    #             wd_logs,
    #             group_key=lambda _: WorkerDay.objects.qos_get_current_worker_day(_).id,
    #             sort_key=lambda _: _.id,
    #             sort_reverse=True
    #         )
    #         '''
    #         indicators_response = {}
    #         if (len(form['worker_ids']) == 1):
    #             indicators_response = {
    #                 'work_day_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_WORKDAY),
    #                 'holiday_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_HOLIDAY),
    #                 'sick_day_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_SICK),
    #                 'vacation_day_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_VACATION),
    #                 'work_day_in_holidays_amount': sum(
    #                     1 for x in worker_days if x.type == WorkerDay.TYPE_WORKDAY and
    #                     x.dt in official_holidays),
    #                 'change_amount': len(worker_day_change_log),
    #                 'hours_count_fact': wd_stat_count_total(worker_days_filter, request.shop)['hours_count_fact']
    #             }
    #         worker_days = list(map(check_wd, worker_days))
    #         days_response = [
    #             {
    #                 'day': WorkerDayConverter.convert(wd),
    #                 'change_log': WorkerDayChangeLogConverter.convert(worker_day_change_log.get(wd.id, [])),
    #                 'change_requests': [],
    #             }
    #             for wd in worker_days
    #         ]
    #
    #         response[worker_id] = {
    #             'indicators': indicators_response,
    #             'days': days_response,
    #             'user': EmploymentConverter.convert(employment)
    #         }
    #     return JsonResponse.success(response)


