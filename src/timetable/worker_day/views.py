import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, F, Exists
from django.db.models.query import Prefetch
from django.http import HttpResponse
from django.utils import timezone
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext_lazy as _
from django_filters import utils
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from src.base.exceptions import FieldError
from src.base.models import Employment, Shop, Employee
from src.base.permissions import WdPermission
from src.base.views_abstract import BaseModelViewSet
from src.events.signals import event_signal
from src.reports.utils.overtimes_undertimes import overtimes_undertimes_xlsx
from src.timetable.backends import MultiShopsFilterBackend
from src.timetable.events import REQUEST_APPROVE_EVENT_TYPE
from src.timetable.filters import WorkerDayFilter, WorkerDayStatFilter, VacancyFilter
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkerDayOutsourceNetwork,
    WorkerDayType,
    TimesheetItem,
)
from src.timetable.vacancy.utils import cancel_vacancies, cancel_vacancy, confirm_vacancy, notify_vacancy_created
from src.timetable.worker_day.serializers import (
    ConfirmVacancyToWorkerSerializer,
    OvertimesUndertimesReportSerializer,
    ChangeListSerializer,
    WorkerDaySerializer,
    WorkerDayApproveSerializer,
    WorkerDayWithParentSerializer,
    VacancySerializer,
    DuplicateSrializer,
    DeleteWorkerDaysSerializer,
    ExchangeSerializer,
    UploadTimetableSerializer,
    GenerateUploadTimetableExampleSerializer,
    DownloadSerializer,
    WorkerDayListSerializer,
    DownloadTabelSerializer,
    ChangeRangeListSerializer,
    CopyApprovedSerializer,
    RequestApproveSerializer,
    CopyRangeSerializer,
    BlockOrUnblockWorkerDayWrapperSerializer,
    RecalcWdaysSerializer,
)
from src.timetable.worker_day.stat import count_daily_stat
from src.timetable.worker_day.tasks import recalc_wdays
from src.timetable.worker_day.timetable import get_timetable_generator_cls
from src.timetable.worker_day.utils.approve import WorkerDayApproveHelper
from src.timetable.worker_day.utils.utils import create_worker_days_range, exchange, \
    copy_as_excel_cells
from src.util.dg.timesheet import get_tabel_generator_cls
from src.util.models_converter import Converter
from src.util.openapi.responses import (
    worker_stat_response_schema_dictionary,
    daily_stat_response_schema_dictionary,
    confirm_vacancy_response_schema_dictionary,
    change_range_response_schema_dictionary,
)
from src.util.upload import get_uploaded_file
from .stat import WorkersStatsGetter


class WorkerDayViewSet(BaseModelViewSet):
    error_messages = {  # вынести из вьюсета
        "worker_days_mismatch": _("Worker days mismatch."),
        "no_timetable": _("Workers don't have timetable."),
        'cannot_delete': _("Cannot_delete approved version."),
        'na_worker_day_exists': _("Not approved version already exists."),
        'no_action_perm_for_wd_type': _('You do not have rights to {action_str} the day type "{wd_type_str}"'),
        'wd_interval_restriction': _('You do not have the rights to {action_str} the type of day "{wd_type_str}" '
                                               'on the selected dates. '
                                               'You need to change the dates. '
                                               'Allowed interval: {dt_interval}'),
        'has_no_perm_to_approve_protected_wdays': _('You do not have rights to approve protected worker days ({protected_wdays}). '
                                                   'Please contact your system administrator.'),
        "no_such_user_in_network": _("There is no such user in your network."),
        "employee_not_in_subordinates": _("Employee {employee} is not your subordinate."),
    }

    permission_classes = [WdPermission]  # временно из-за биржи смен vacancy  [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    filter_backends = [MultiShopsFilterBackend]
    openapi_tags = ['WorkerDay',]

    def get_queryset(self):
        queryset = WorkerDay.objects.filter(canceled=False).prefetch_related(Prefetch('outsources', to_attr='outsources_list'))

        if self.request.query_params.get('by_code', False):
            return queryset.annotate(
                shop_code=F('shop__code'),
                user_login=F('employee__user__username'),
                employment_tabel_code=F('employee__tabel_code'),
            )

        return queryset

    # тут переопределяется update а не perform_update потому что надо в Response вернуть
    # не тот объект, который был изначально
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        if instance.is_approved:
            if instance.child.filter(is_fact=instance.is_fact):
                raise FieldError(self.error_messages['na_worker_day_exists'])

            data = serializer.validated_data
            data['parent_worker_day_id'] = instance.id
            data['is_fact'] = instance.is_fact
            serializer = WorkerDayWithParentSerializer(data=data)
            serializer.is_valid(raise_exception=True)

        serializer.save()

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def perform_destroy(self, worker_day):
        if worker_day.is_vacancy and not worker_day.is_fact:
            cancel_vacancy(worker_day.id, auto=False)
            return
        if worker_day.is_approved:
            raise FieldError(self.error_messages['cannot_delete'])
        super().perform_destroy(worker_day)

    def list(self, request, *args, **kwargs):
        if request.query_params.get('hours_details', False):
            data = []

            worker_days = self.filter_queryset(
                self.get_queryset().prefetch_related(
                    Prefetch('worker_day_details', to_attr='worker_day_details_list')
                ).select_related(
                    'last_edited_by',
                    'shop__network__breaks',
                    'employee',
                    'shop__settings__breaks',
                    'employment__position__breaks',
                    'closest_plan_approved',
                )
            )

            for worker_day in worker_days:
                wd_dict = WorkerDayListSerializer(worker_day, context=self.get_serializer_context()).data
                work_hours, work_hours_day, work_hours_night = worker_day.calc_day_and_night_work_hours()
                wd_dict['work_hours'] = work_hours
                wd_dict['work_hours_details'] = {
                    'D': work_hours_day,
                    'N': work_hours_night,
                }
                data.append(wd_dict)
        else:
            data = WorkerDayListSerializer(
                self.filter_queryset(self.get_queryset().prefetch_related(Prefetch('worker_day_details', to_attr='worker_day_details_list')).select_related('last_edited_by', 'employee')),
                many=True, context=self.get_serializer_context()
            ).data

        if request.query_params.get('fill_empty_days', False):
            employment__tabel_code__in = [
                i for i in request.query_params.get('employment__tabel_code__in', '').split(',') if i]
            employee_id__in = [i for i in request.query_params.get('employee_id__in', '').split(',') if i]
            dt__gte = request.query_params.get('dt__gte')
            dt__lte = request.query_params.get('dt__lte')
            if (employment__tabel_code__in or employee_id__in) and dt__gte and dt__lte:
                response_wdays_dict = {f"{d['employee_id']}_{d['dt']}": d for d in data}

                employees = Employee.objects
                if employee_id__in:
                    employees = employees.filter(id__in=employee_id__in)
                elif employment__tabel_code__in:
                    employees = employees.filter(tabel_code__in=employment__tabel_code__in)

                plan_wdays_dict = {f'{wd.employee_id}_{wd.dt}': wd for wd in WorkerDay.objects.filter(
                    employee__in=employees,
                    dt__gte=dt__gte,
                    dt__lte=dt__lte,
                    is_approved=True,
                    is_fact=False,
                ).exclude(
                    type_id=WorkerDay.TYPE_EMPTY,
                ).select_related(
                    'employee__user',
                    'shop',
                    'type',
                )}
                for employee in employees:
                    for dt in pd.date_range(dt__gte, dt__lte).date:
                        empl_dt_key = f"{employee.id}_{dt}"
                        resp_wd = response_wdays_dict.get(empl_dt_key)
                        if resp_wd:  # если есть ответ для сотрудника на конкретный день, то пропускаем
                            continue

                        plan_wd = plan_wdays_dict.get(empl_dt_key)

                        # Если нет ни плана ни факта, то добавляем выходной
                        if not plan_wd:
                            d = {
                                "id": None,
                                "worker_id": employee.user_id,
                                "employee_id": employee.id,
                                "shop_id": None,
                                "employment_id": None,  # нужен?
                                "type": "H",
                                "dt": Converter.convert_date(dt),
                                "dttm_work_start": None,
                                "dttm_work_end": None,
                                "dttm_work_start_tabel": None,
                                "dttm_work_end_tabel": None,
                                "comment": None,
                                "is_approved": None,
                                "worker_day_details": [],
                                "outsources": [],
                                "is_fact": None,
                                "work_hours": 0,
                                "parent_worker_day_id": None,
                                "created_by_id": None,
                                "last_edited_by": None,
                                "dttm_modified": None,
                                "is_blocked": None
                            }
                            if self.request.query_params.get('by_code', False):
                                d['shop_code'] = None
                                d['user_login'] = employee.user.username
                                d['employment_tabel_code'] = employee.tabel_code
                            data.append(d)
                            continue

                        dt_now = timezone.now().date()
                        if plan_wd and not plan_wd.type.is_dayoff:
                            day_in_past = dt < dt_now
                            d = {
                                "id": None,
                                "worker_id": employee.user_id,
                                "employee_id": employee.id,
                                "shop_id": plan_wd.shop_id,
                                "employment_id": plan_wd.employment_id,
                                "type": WorkerDay.TYPE_ABSENSE if day_in_past else WorkerDay.TYPE_WORKDAY,
                                "dt": Converter.convert_date(dt),
                                "dttm_work_start": None,
                                "dttm_work_end": None,
                                "dttm_work_start_tabel": None,
                                "dttm_work_end_tabel": None,
                                "comment": None,
                                "is_approved": None,
                                "worker_day_details": None,
                                "outsources": None,
                                "is_fact": None,
                                "work_hours": 0,
                                "parent_worker_day_id": None,
                                "created_by_id": None,
                                "last_edited_by": None,
                                "dttm_modified": None,
                                "is_blocked": None,
                            }
                            if not day_in_past:
                                d["work_hours_details"] = {
                                  "D": 0
                                }
                            if self.request.query_params.get('by_code', False):
                                d['shop_code'] = plan_wd.shop.code
                                d['user_login'] = employee.user.username
                                d['employment_tabel_code'] = employee.tabel_code
                            data.append(d)

        return Response(data)

    @action(detail=False, methods=['post'])
    def request_approve(self, request, *args, **kwargs):
        """
        Запрос на подтверждение графика
        """
        serializer = RequestApproveSerializer(data=request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        event_context = serializer.data.copy()
        transaction.on_commit(lambda: event_signal.send(
            sender=None,
            network_id=request.user.network_id,
            event_code=REQUEST_APPROVE_EVENT_TYPE,
            user_author_id=request.user.id,
            shop_id=serializer.data['shop_id'],
            context=event_context,
        ))
        return Response({})

    @swagger_auto_schema(
        request_body=WorkerDayApproveSerializer,
        responses={200: 'empty response'},
        operation_description='''
        Метод для подтверждения графика
        ''',
    )
    @action(detail=False, methods=['post'])
    def approve(self, request):
        kwargs = {'context': self.get_serializer_context()}
        serializer = WorkerDayApproveSerializer(data=request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        wd_approve_helper = WorkerDayApproveHelper(user=self.request.user, **serializer.validated_data)
        wd_approve_helper.run()
        return Response()

    @swagger_auto_schema(
        operation_description='''
        Возвращает статистику по сотрудникам
        ''',
        responses=worker_stat_response_schema_dictionary,
    )
    @action(detail=False, methods=['get'], filterset_class=WorkerDayStatFilter)
    def worker_stat(self, request):
        filterset = WorkerDayStatFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        stat = WorkersStatsGetter(**data).run()
        return Response(stat)

    @swagger_auto_schema(
        operation_description='''
        Возвращает статистику по дням
        ''',
        responses=daily_stat_response_schema_dictionary,
    )
    @action(detail=False, methods=['get'], filterset_class=WorkerDayStatFilter)
    def daily_stat(self, request):
        filterset = WorkerDayStatFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        stat = count_daily_stat(data)
        return Response(stat)

    @swagger_auto_schema(
        operation_description='''
        Возвращает вакансии
        ''',
    )
    @action(detail=False, methods=['get'], filterset_class=VacancyFilter)
    def vacancy(self, request):
        filterset_class = VacancyFilter(request.query_params, request=request)
        if not filterset_class.form.is_valid():
            raise utils.translate_validation(filterset_class.errors)
        
        paginator = LimitOffsetPagination()
        allowed_outsource_network_subq = WorkerDayOutsourceNetwork.objects.filter(
            workerday_id=OuterRef('id'),
            network_id=self.request.user.network_id,
        )
        dt = datetime.date.today()
        user_shops = list(request.user.get_shops(include_descendants=True).values_list('id', flat=True))
        available_employee = list(
            request.user.get_subordinates(
                dt=dt,
                dt_to_shift=relativedelta(months=6),
                user_shops=user_shops,
            ).values_list('id', flat=True)
        ) + list(
            request.user.get_active_employments(
                dt_from=dt,
                dt_to=dt + relativedelta(months=6),
            ).values_list('employee_id', flat=True)
        )
        queryset = filterset_class.filter_queryset(
            self.get_queryset().filter(
                is_vacancy=True,
                type__is_work_hours=True,
            ).annotate(
                outsource_network_allowed=Exists(allowed_outsource_network_subq),
            ).filter(
                (
                    Q(shop__network_id=request.user.network_id)&
                    (
                        Q(is_outsource=True) | Q(employee__isnull=True) |
                        Q(employee_id__in=available_employee) |
                        Q(shop_id__in=user_shops)
                    )
                ) | 
                (
                    Q(is_outsource=True, outsource_network_allowed=True, is_approved=True) &
                    (Q(employee__isnull=True) | Q(employee__user__network_id=request.user.network_id)) # чтобы не попадали вакансии с сотрудниками другой аутсорс сети
                ), # аутсорс фильтр
            ).select_related(
                'shop',
                'employee__user',
            ).prefetch_related(
                'worker_day_details',
                'outsources',
            ).annotate(
                first_name=F('employee__user__first_name'),
                last_name=F('employee__user__last_name'),
                worker_shop=Subquery(
                    Employment.objects.get_active(
                        OuterRef('employee__user__network_id'),
                        employee_id=OuterRef('employee_id')
                    ).values('shop_id')[:1]
                ),
                user_network_id=F('employee__user__network_id'),
            ),
        )
        data = paginator.paginate_queryset(queryset, request)
        data = VacancySerializer(data, many=True, context=self.get_serializer_context())

        return paginator.get_paginated_response(data.data)

    @swagger_auto_schema(
        operation_description='''
        Метод для выхода на вакансию
        ''',
        responses=confirm_vacancy_response_schema_dictionary,
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def confirm_vacancy(self, request, pk=None):
        result = confirm_vacancy(pk, request.user, employee_id=self.request.data.get('employee_id', None))
        status_code = result['status_code']
        result = result['text']

        return Response({'result': result}, status=status_code)

    @swagger_auto_schema(
        operation_description='''
        Метод для вывывода на вакансию сотрудника
        ''',
        responses=confirm_vacancy_response_schema_dictionary,
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def confirm_vacancy_to_worker(self, request, pk=None):
        data = ConfirmVacancyToWorkerSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        data = data.validated_data
        result = confirm_vacancy(pk, data['user'], employee_id=data['employee_id'])
        status_code = result['status_code']
        result = result['text']

        return Response({'result': result}, status=status_code)

    @swagger_auto_schema(
        operation_description='''
        Метод для переназначения сотрудника на вакансию
        ''',
        responses=confirm_vacancy_response_schema_dictionary,
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def reconfirm_vacancy_to_worker(self, request, pk=None):
        data = ConfirmVacancyToWorkerSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        data = data.validated_data
        result = confirm_vacancy(pk, data['user'], employee_id=data['employee_id'], reconfirm=True)
        status_code = result['status_code']
        result = result['text']

        return Response({'result': result}, status=status_code)
    
    @swagger_auto_schema(
        operation_description='''
        Метод для отказа от вакансии
        ''',
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def refuse_vacancy(self, request, pk=None):
        result = confirm_vacancy(pk, refuse=True)
        status_code = result['status_code']
        result = result['text']

        return Response({'result': result}, status=status_code)

    @swagger_auto_schema(
        operation_description='''
        Метод для подтверждения вакансии
        ''',
    )
    @action(detail=True, methods=['post'])
    def approve_vacancy(self, request, pk=None):
        with transaction.atomic():
            vacancy = WorkerDay.objects.filter(pk=pk, is_vacancy=True, is_approved=False).select_for_update().first()
            if vacancy is None:
                raise ValidationError(_('This vacancy does not exist or has already been approved.'))

            if vacancy.shop.network_id != request.user.network_id:
                raise ValidationError(_('You can not approve vacancy from other network.'))

            if vacancy.employee_id:
                WorkerDay.objects_with_excluded.filter(
                    dt=vacancy.dt,
                    employee_id=vacancy.employee_id,
                    is_fact=vacancy.is_fact,
                    is_approved=True,
                ).exclude(id=vacancy.id).delete()
                vacancy.parent_worker_day_id = None # так как выше удаляем возможного родителя
                vacancy.is_approved = True
                vacancy.save()

                vacancy_details = WorkerDayCashboxDetails.objects.filter(
                    worker_day=vacancy).values('work_type_id', 'work_part')

                parent_id = vacancy.id
                outsources = list(vacancy.outsources.all())
                vacancy.id = None
                vacancy.parent_worker_day_id = parent_id
                vacancy.is_approved = False
                vacancy.source = WorkerDay.SOURCE_ON_APPROVE
                vacancy.save()
                vacancy.outsources.add(*outsources)

                WorkerDayCashboxDetails.objects.bulk_create(
                    WorkerDayCashboxDetails(
                        worker_day=vacancy,
                        work_type_id=details['work_type_id'],
                        work_part=details['work_part'],
                    ) for details in vacancy_details
                )

                WorkerDay.set_closest_plan_approved(
                    q_obj=Q(employee_id=vacancy.employee_id, dt=vacancy.dt),
                    delta_in_secs=vacancy.shop.network.set_closest_plan_approved_delta_for_manual_fact,
                )
                transaction.on_commit(lambda: recalc_wdays.delay(
                    id__in=list(WorkerDay.objects.filter(closest_plan_approved=parent_id).values_list('id', flat=True))))
            else:
                transaction.on_commit(lambda: notify_vacancy_created(vacancy, is_auto=False))
                vacancy.is_approved = True
                vacancy.save()

        return Response(WorkerDaySerializer(vacancy).data)

    @swagger_auto_schema(
        operation_description='''
        Метод для получения редактируемой версии вакансии
        ''',
    )
    @action(detail=True, methods=['get'])
    def editable_vacancy(self, request, pk=None):
        vacancy = WorkerDay.objects.filter(pk=pk, is_vacancy=True).first()
        if vacancy is None:
            raise ValidationError(_('There is no such vacancy.'))
        if not vacancy.is_approved:
            return Response(WorkerDaySerializer(vacancy).data)
        if vacancy.employee_id:
            raise ValidationError(_('The vacancy cannot be edited because it has already been responded.'))

        vacancy.is_approved = False  # "расподтверждаем" открытую подтвержденную вакансию перед редактированием
        vacancy.save()
        return Response(WorkerDaySerializer(vacancy).data)

    def _change_range(self, is_fact, is_approved, is_blocked, dt_from, dt_to, wd_type, employee_tabel_code, res=None):
        employee_dt_pairs_list = list(WorkerDay.objects.filter(
            employee__tabel_code=employee_tabel_code,
            dt__gte=dt_from,
            dt__lte=dt_to,
            is_approved=is_approved,
            is_blocked=is_blocked,
            is_fact=is_fact,
            type=wd_type,
        ).values_list('employee_id', 'dt').distinct())
        employee_dt_pairs_q = Q()
        existing_dates = []
        for employee_id, dt in employee_dt_pairs_list:
            employee_dt_pairs_q |= Q(employee_id=employee_id, dt=dt)
            existing_dates.append(dt)

        to_delete_qs = WorkerDay.objects.filter(
            employee__tabel_code=employee_tabel_code,
            dt__gte=dt_from,
            dt__lte=dt_to,
            is_approved=is_approved,
            is_fact=is_fact,
        ).exclude(
            employee_dt_pairs_q,
        )
        if not is_fact and is_approved:
            related_fact_ids = list(to_delete_qs.values_list('related_facts__id', flat=True))
            if related_fact_ids:
                transaction.on_commit(lambda: recalc_wdays.delay(id__in=related_fact_ids))
        deleted = to_delete_qs.delete()

        wdays_to_create = []
        for dt in [d.date() for d in pd.date_range(dt_from, dt_to)]:
            if dt not in existing_dates:
                employment = Employment.objects.get_active_empl_by_priority(
                    network_id=self.request.user.network_id,
                    dt=dt,
                    employee__tabel_code=employee_tabel_code,
                ).first()
                if employment:
                    wdays_to_create.append(
                        WorkerDay(
                            employment=employment,
                            employee_id=employment.employee_id,
                            dt=dt,
                            is_approved=is_approved,
                            is_blocked=is_blocked,
                            is_fact=is_fact,
                            type=wd_type,
                            created_by=self.request.user,
                            need_count_wh=True,
                            source=WorkerDay.SOURCE_CHANGE_RANGE,
                        )
                    )
        WorkerDay.objects.bulk_create(wdays_to_create)

        if res is not None:
            employee_stats = res.setdefault(employee_tabel_code, {})
            employee_stats['deleted_count'] = employee_stats.get(
                'deleted_count', 0) + deleted[1].get('timetable.WorkerDay', 0)
            employee_stats['existing_count'] = employee_stats.get('existing_count', 0) + len(existing_dates)
            employee_stats['created_count'] = employee_stats.get('created_count', 0) + len(wdays_to_create)

    @swagger_auto_schema(
        request_body=ChangeRangeListSerializer,
        operation_description='''
        Метод для создания/обновления дней за период
        Обычно используется для получения отпусков/больничных из 1С ЗУП
        ''',
        responses=change_range_response_schema_dictionary,
    )
    @action(detail=False, methods=['post'])
    def change_range(self, request):
        with transaction.atomic():
            serializer = ChangeRangeListSerializer(data=request.data, context=self.get_serializer_context())
            serializer.is_valid(raise_exception=True)

            res = {}
            for range in serializer.validated_data['ranges']:
                self._change_range(
                    is_fact=False,  # всегда в план
                    is_approved=range['is_approved'],
                    is_blocked=range.get('is_blocked', False),
                    dt_from=range['dt_from'],
                    dt_to=range['dt_to'],
                    wd_type=range['type'],
                    employee_tabel_code=range['worker'],
                    res=res,
                )
                if range['is_approved']:
                    self._change_range(
                        is_fact=False,  # всегда в план
                        is_approved=False,
                        is_blocked=range.get('is_blocked', False),
                        dt_from=range['dt_from'],
                        dt_to=range['dt_to'],
                        wd_type=range['type'],
                        employee_tabel_code=range['worker'],
                    )

        return Response(res)

    @swagger_auto_schema(
        request_body=CopyApprovedSerializer,
        operation_description='''
        Метод для копирования подтвержденных рабочих дней в черновик
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def copy_approved(self, request):
        data = CopyApprovedSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        with transaction.atomic():
            is_copying_from_fact = data['type'] == CopyApprovedSerializer.TYPE_FACT_TO_FACT
            source_wdays_filter_q = Q(is_fact=is_copying_from_fact)
            if data['type'] == CopyApprovedSerializer.TYPE_PLAN_TO_FACT:
                source_wdays_filter_q &= Q(Q(type__is_dayoff=False) | Q(type_id=WorkerDay.TYPE_EMPTY))
            source_wdays_list = list(
                WorkerDay.objects.filter(
                    source_wdays_filter_q,
                    dt__in=data['dates'],
                    employee_id__in=data['employee_ids'],
                    is_approved=True,
                ).select_related(
                    'shop', 
                    'type',
                    'employment',
                    'employment__position', 
                    'employment__position__breaks',
                    'shop__settings__breaks',
                ).prefetch_related(
                    'worker_day_details',
                    Prefetch(
                        'outsources',
                        to_attr='outsources_list',
                    ),
                )
            )
            is_copying_to_fact = data['type'] in (
                CopyApprovedSerializer.TYPE_PLAN_TO_FACT, CopyApprovedSerializer.TYPE_FACT_TO_FACT)

            if data['type'] == CopyApprovedSerializer.TYPE_PLAN_TO_FACT and request.user.network.copy_plan_to_fact_crossing:
                grouped_wds = {}
                for wd in source_wdays_list:
                    k = f'{wd.employee_id}_{wd.dt}'
                    grouped_wds.setdefault(k, []).append(wd)

                wds_approved = WorkerDay.objects_with_excluded.filter(
                    dt__in=data['dates'],
                    employee_id__in=data['employee_ids'],
                    is_approved=True,
                    is_fact=True,
                ).select_related(
                    'shop',
                    'type',
                    'employment',
                    'employment__position',
                    'employment__position__breaks',
                    'shop__settings__breaks',
                ).prefetch_related(
                    'worker_day_details',
                    Prefetch(
                        'outsources',
                        to_attr='outsources_list',
                    ),
                )
                popped_keys = set()
                for wd in wds_approved:
                    k = f'{wd.employee_id}_{wd.dt}'
                    if k in grouped_wds and k not in popped_keys:
                        grouped_wds.pop(k)
                    grouped_wds.setdefault(k, []).append(wd)
                source_wdays_list = [wd for wdays_list in grouped_wds.values() for wd in wdays_list]

            wdays = []
            for wd in source_wdays_list:
                wd_data = dict(
                    shop_id=wd.shop_id,
                    employee_id=wd.employee_id,
                    employment_id=wd.employment_id,
                    work_hours=wd.work_hours,
                    dttm_work_start=wd.dttm_work_start,
                    dttm_work_end=wd.dttm_work_end,
                    dt=wd.dt,
                    is_fact=is_copying_to_fact,
                    is_approved=False,
                    type=wd.type,
                    created_by=wd.created_by if (wd.is_fact and wd.is_approved) else self.request.user,
                    last_edited_by=wd.last_edited_by if (wd.is_fact and wd.is_approved) else self.request.user,
                    is_vacancy=wd.is_vacancy,
                    is_outsource=wd.is_outsource,
                    comment=wd.comment,
                    canceled=wd.canceled,
                    parent_worker_day_id=wd.id,
                    closest_plan_approved_id=wd.id if (
                            is_copying_to_fact and wd.is_plan and wd.is_approved) else wd.closest_plan_approved_id,
                    source=data['source'],
                )
                if not is_copying_to_fact:
                    wd_data['outsources'] = [dict(network_id=network.id) for network in wd.outsources_list]
                wd_data['worker_day_details'] = [
                    dict(
                        work_type_id=wd_cashbox_details_parent.work_type_id,
                        work_part=wd_cashbox_details_parent.work_part,
                    )
                    for wd_cashbox_details_parent in wd.worker_day_details.all()
                ]
                wdays.append(wd_data)
            WorkerDay.batch_update_or_create(
                wdays, 
                user=self.request.user, 
                generate_delete_scope_values=False,
                delete_scope_filters=dict(
                    is_fact=is_copying_to_fact,
                    dt__in=data['dates'],
                    employee_id__in=data['employee_ids'],
                    is_approved=False,
                ),
                check_perms_extra_kwargs=dict(
                    grouped_checks=True,
                ),
            )

            copied_wdays_qs = WorkerDay.objects.filter(
                is_fact=is_copying_to_fact,
                is_approved=False,
                dt__in=data['dates'],
                employee_id__in=data['employee_ids'],
            )

        return Response(WorkerDayListSerializer(copied_wdays_qs.prefetch_related(Prefetch('worker_day_details', to_attr='worker_day_details_list')).select_related('last_edited_by'), many=True, context={'request':request}).data)

    @swagger_auto_schema(
        request_body=DuplicateSrializer,
        operation_description='''
        Метод для копирования рабочих дней
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def duplicate(self, request):
        data = DuplicateSrializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        to_employee_id = data['to_employee_id']
        from_employee_id = data['from_employee_id']

        with transaction.atomic():
            created_wds, work_types = copy_as_excel_cells(
                from_employee_id=from_employee_id,
                from_dates=data['from_dates'],
                to_employee_id=to_employee_id,
                to_dates=data['to_dates'],
                user=request.user,
                is_approved=data['is_approved'],
            )
            for shop_id, work_type in set(work_types):
                cancel_vacancies(shop_id, work_type)

        return Response(WorkerDaySerializer(created_wds, many=True).data)

    @swagger_auto_schema(
        request_body=CopyRangeSerializer,
        operation_description='''
        Метод для копирования рабочих дней
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def copy_range(self, request):
        data = CopyRangeSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        from_dates = data['from_dates']
        to_dates = data['to_dates']
        employee_ids = data.get('employee_ids', [])
        created_wds = []
        work_types = []
        with transaction.atomic():
            for employee_id in employee_ids:
                wds, w_types = copy_as_excel_cells(
                    employee_id,
                    from_dates,
                    employee_id,
                    to_dates,
                    user=request.user,
                    is_approved=data['is_approved'],
                    include_spaces=True,
                    worker_day_types=data['worker_day_types'],
                )

                created_wds.extend(wds)
                work_types.extend(w_types)

            for shop_id, work_type in set(work_types):
                cancel_vacancies(shop_id, work_type)

        return Response(WorkerDaySerializer(created_wds, many=True).data)

    @swagger_auto_schema(
        request_body=DeleteWorkerDaysSerializer,
        operation_description='''
        Метод для удаления рабочих дней
        ''',
        responses={200: 'empty response'},
    )
    @action(detail=False, methods=['post'])
    def delete_worker_days(self, request):
        with transaction.atomic():
            data = DeleteWorkerDaysSerializer(data=request.data, context={'request': request})
            data.is_valid(raise_exception=True)
            data = data.validated_data
            filt = {}
            q_filt = Q()
            if data['exclude_created_by']:
                filt['created_by__isnull'] = True
            if data.get('shop_id'):
                q_filt |= Q(shop_id=data['shop_id']) | Q(shop__isnull=True)
            wdays_qs = WorkerDay.objects_with_excluded.filter(
                q_filt,
                is_approved=False,
                is_fact=data['is_fact'],
                employee_id__in=data['employee_ids'],
                dt__in=data['dates'],
                **filt,
            )
            deleted_wdays = list(wdays_qs)
            delete_values = list(map(lambda x: (x.dt, x.employee_id, x.employment_id, x.shop_id, x.type_id, x.is_fact, x.is_vacancy), deleted_wdays))
            grouped_perm_check_data = WorkerDay._get_grouped_perm_check_data(delete_values)
            for wd_data in grouped_perm_check_data:
                WorkerDay._check_delete_single_wd_data_perm(self.request.user, wd_data)
            wdays_qs.delete()
            WorkerDay._invalidate_cache(deleted_objs=deleted_wdays)

        return Response()

    @swagger_auto_schema(
        request_body=ExchangeSerializer,
        operation_description='''
        Метод для обмена рабочими сменами в черновике
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def exchange(self, request):
        with transaction.atomic():
            data = ExchangeSerializer(data=request.data, context={'request': request})
            data.is_valid(raise_exception=True)
            data = data.validated_data
            data['is_approved'] = False
            data['user'] = request.user

            res = Response(WorkerDaySerializer(exchange(data, self.error_messages), many=True).data)
        return res

    @swagger_auto_schema(
        request_body=ExchangeSerializer,
        operation_description='''
        Метод для обмена подтвержденными рабочими сменами
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def exchange_approved(self, request):
        with transaction.atomic():
            data = ExchangeSerializer(data=request.data, context={'request': request})
            data.is_valid(raise_exception=True)
            data = data.validated_data
            data['is_approved'] = True
            data['user'] = request.user

            res = Response(WorkerDaySerializer(exchange(data, self.error_messages), many=True).data)

            WorkerDay.check_work_time_overlap(
                employee_id__in=[data['employee1_id'], data['employee2_id']],
                dt__in=data['dates'],
                exc_cls=ValidationError,
            )

        return res

    @swagger_auto_schema(
        request_body=UploadTimetableSerializer,
        responses={200: 'empty response'},
        operation_description='''
        Загружает плановое расписание в систему.\n
        Должен быть прикреплён файл с расписанием в формате excel в поле file.
        ''',
    )
    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload(self, request, file):
        data = UploadTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.validated_data['network_id'] = request.user.network_id
        shop = Shop.objects.get(id=data.validated_data.get('shop_id'))
        timetable_generator_cls = get_timetable_generator_cls(timetable_format=shop.network.timetable_format)
        timetable_generator = timetable_generator_cls(user=self.request.user, form=data.validated_data)
        return timetable_generator.upload(file)

    @swagger_auto_schema(
        query_serializer=GenerateUploadTimetableExampleSerializer,
        responses={200: 'Шаблон расписания в формате excel.'},
        operation_description='''
            Возвращает шаблон для загрузки графика.\n
            ''',
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def generate_upload_example(self, request):
        # TODO: рефакторинг + тест
        serializer = GenerateUploadTimetableExampleSerializer(
            data=request.query_params if request.method == 'GET' else request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)

        shop_id = serializer.validated_data.get('shop_id')
        dt_from = serializer.validated_data.get('dt_from')
        dt_to = serializer.validated_data.get('dt_to')
        is_fact = serializer.validated_data.get('is_fact')
        is_approved = serializer.validated_data.get('is_approved')
        employee_id__in = serializer.validated_data.get('employee_id__in')

        shop = Shop.objects.get(id=shop_id)
        timetable_generator_cls = get_timetable_generator_cls(timetable_format=shop.network.timetable_format)
        timetable_generator = timetable_generator_cls(user=self.request.user, form=serializer.validated_data)
        return timetable_generator.generate_upload_example(shop_id, dt_from, dt_to, is_fact, is_approved, employee_id__in)

    @swagger_auto_schema(
        request_body=UploadTimetableSerializer,
        responses={200: 'empty response'},
        operation_description='''
        Загружает фактическое расписание в систему.\n
        Должен быть прикреплён файл с расписанием в формате excel в поле file.
        ''',
    )
    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload_fact(self, request, file):
        data = UploadTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.validated_data['network_id'] = request.user.network_id
        shop = Shop.objects.get(id=data.validated_data.get('shop_id'))
        timetable_generator_cls = get_timetable_generator_cls(timetable_format=shop.network.timetable_format)
        timetable_generator = timetable_generator_cls(user=self.request.user, form=data.validated_data)
        return timetable_generator.upload(file, is_fact=True)

    @swagger_auto_schema(
        query_serializer=DownloadSerializer,
        responses={200:'Файл с расписанием в формате excel.'},
        operation_description='''
        Метод для скачивания графика работы сотрудников.
        ''',
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def download_timetable(self, request):
        data = DownloadSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        shop = Shop.objects.get(id=data.validated_data.get('shop_id'))
        timetable_generator_cls = get_timetable_generator_cls(timetable_format=shop.network.timetable_format)
        timetable_generator = timetable_generator_cls(user=self.request.user, form=data.validated_data)
        return timetable_generator.download()

    @swagger_auto_schema(
        query_serializer=DownloadSerializer,
        responses={200:'Файл с табелем'},
        operation_description='''
        Метод для скачивания табеля для подразделения.
        '''
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def download_tabel(self, request):
        serializer = DownloadTabelSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        shop = Shop.objects.get(id=serializer.validated_data.get('shop_id'))
        dt_from = serializer.validated_data.get('dt_from')
        dt_to = serializer.validated_data.get('dt_to')
        convert_to = serializer.validated_data.get('convert_to')
        timesheet_type = serializer.validated_data.get('tabel_type')
        tabel_generator_cls = get_tabel_generator_cls(tabel_format=shop.network.download_tabel_template)
        tabel_generator = tabel_generator_cls(shop, dt_from, dt_to, timesheet_type=timesheet_type)
        response = HttpResponse(
            tabel_generator.generate(convert_to=shop.network.convert_tabel_to or convert_to),
            content_type='application/octet-stream',
        )
        filename = _('{}_timesheet_for_shop_{}_from_{}.{}').format(
            dict(TimesheetItem.TIMESHEET_TYPE_CHOICES).get(timesheet_type, ''),
            shop.code,
            timezone.now().strftime("%Y-%m-%d"),
            shop.network.convert_tabel_to or convert_to,
        )
        response['Content-Disposition'] = f'attachment; filename={escape_uri_path(filename)}'
        return response

    @swagger_auto_schema(
        request_body=BlockOrUnblockWorkerDayWrapperSerializer,
        responses={200: None},
        operation_description='''
            Заблокировать рабочий день.
            '''
    )
    @action(detail=False, methods=['post'], filterset_class=None)
    def block(self, request):
        serializer = BlockOrUnblockWorkerDayWrapperSerializer(
            data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        for dict_to_block in serializer.validated_data['worker_days']:
            WorkerDay.objects.filter(
                employee_id=dict_to_block['employee_id'],
                shop_id=dict_to_block['shop_id'],
                dt=dict_to_block['dt'],
                is_fact=dict_to_block['is_fact'],
            ).update(is_blocked=True)
        return Response()

    @swagger_auto_schema(
        request_body=BlockOrUnblockWorkerDayWrapperSerializer,
        responses={200: None},
        operation_description='''
            Разблокировать рабочий день.
            '''
    )
    @action(detail=False, methods=['post'], filterset_class=None)
    def unblock(self, request):
        serializer = BlockOrUnblockWorkerDayWrapperSerializer(
            data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        for dict_to_block in serializer.validated_data['worker_days']:
            WorkerDay.objects.filter(
                employee_id=dict_to_block['employee_id'],
                shop_id=dict_to_block['shop_id'],
                dt=dict_to_block['dt'],
                is_fact=dict_to_block['is_fact'],
            ).update(is_blocked=False)
        return Response()

    @swagger_auto_schema(
        request_body=RecalcWdaysSerializer,
        responses={200: None},
        operation_description='''
        Пересчет часов
        '''
    )
    @action(detail=False, methods=['post'])
    def recalc(self, *args, **kwargs):
        serializer = RecalcWdaysSerializer(
            data=self.request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        employee_filter = {}
        if serializer.validated_data.get('employee_id__in'):
            employee_filter['employee_id__in'] = serializer.validated_data['employee_id__in']
        employee_ids = Employment.objects.get_active(
            Shop.objects.get(id=serializer.validated_data['shop_id']).network_id,
            dt_from=serializer.validated_data['dt_from'],
            dt_to=serializer.validated_data['dt_to'],
            shop_id=serializer.validated_data['shop_id'],
            **employee_filter,
        ).values_list('employee_id', flat=True)
        employee_ids = list(employee_ids)
        if not employee_ids:
            raise ValidationError({'detail': _('No employees satisfying the conditions.')})
        recalc_wdays.delay(
            employee_id__in=employee_ids,
            dt__gte=serializer.data['dt_from'],
            dt__lte=serializer.data['dt_to'],
        )
        return Response({'detail': _('Hours recalculation started successfully.')})

    @swagger_auto_schema(
        query_serializer=OvertimesUndertimesReportSerializer,
        responses={200: None},
        operation_description='''
        Скачать отчет о переработках/недоработках.
        '''
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def overtimes_undertimes_report(self, request):
        data = OvertimesUndertimesReportSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        output = overtimes_undertimes_xlsx(
            period_step=request.user.network.accounting_period_length,
            employee_id__in=data.get('employee_id__in'),
            shop_ids=[data.get('shop_id')] if data.get('shop_id') else None,
            in_memory=True,
        )
        response = HttpResponse(
            output['file'],
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path('Overtimes_undertimes'))
        return response

    @swagger_auto_schema(
        request_body=ChangeListSerializer,
        responses={200: None},
        operation_description='''
        Проставление типов дней на промежуток для сотрудника
        '''
    )
    @action(detail=False, methods=['post'])
    def change_list(self, request):
        wd_types_dict = WorkerDayType.get_wd_types_dict()
        data = ChangeListSerializer(
            data=request.data, context={'request': request, 'wd_types_dict': wd_types_dict})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        response = WorkerDaySerializer(
            create_worker_days_range(
                data['dates'], 
                type_id=data['type_id'],
                employee_id=data.get('employee_id'),
                shop_id=data['shop_id'],
                tm_work_start=data.get('tm_work_start'),
                tm_work_end=data.get('tm_work_end'),
                is_vacancy=data['is_vacancy'],
                outsources=data['outsources'],
                cashbox_details=data.get('cashbox_details', []),
                created_by=data['created_by'],
            ),
            many=True,
        ).data
        return Response(response)
