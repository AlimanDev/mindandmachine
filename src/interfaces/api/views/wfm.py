import logging
from datetime import timedelta
from django_filters import utils
from django.conf import settings
from django.db.models import Prefetch, Q, Exists, OuterRef
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import (
    viewsets,
    filters,
    permissions,
)
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from src.apps.base.models import (
    Employment,
    Employee,
    User as WFMUser
)
from src.apps.recognition.authentication import ShopIPAuthentication, TickPointTokenAuthentication
from src.interfaces.api.serializers.wfm import WfmWorkerDaySerializer, WorkShiftSerializer
from src.apps.timetable.models import WorkerDay
from src.apps.recognition.wfm.filters import WorkShiftFilter
logger = logging.getLogger('django')
USERS_WITH_SCHEDULE_ONLY = getattr(settings, 'USERS_WITH_SCHEDULE_ONLY', True)


class WorkerDayViewSet(viewsets.ReadOnlyModelViewSet):
    """
        GET /api/v1/worker_days/
        Список сотрудников с расписанием
        [{  "worker_day_id":3211,
            "user_id":46,
            "first_name":"Иван",
            "last_name":"Иванов",
            "dttm_work_start":"2019-10-29T10:00:00Z",
            "dttm_work_end":"2019-10-29T19:00:00Z",
            "avatar":"https://site.mindandmachine.ru/image/123.jpg"
        },
        ...
        ]
    """
    permission_classes = [permissions.IsAuthenticated]
    basename = ''
    openapi_tags = ['RecognitionWorkerDay',]

    serializer_class = WfmWorkerDaySerializer
    # search_fields = ['first_name', 'last_name']
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    def get_authenticators(self):
        return [ShopIPAuthentication(), TickPointTokenAuthentication(raise_auth_exc=False), TokenAuthentication()]

    # filterset_class = WorkerDayFilterSet
    def get_queryset(self):
        shop = self.request.user.shop

        dt_from = (now() + timedelta(hours=shop.get_tz_offset())).date()

        wd_cond = WorkerDay.objects.filter(
            Q(dt=dt_from, dttm_work_start__isnull=False, dttm_work_end__isnull=False) |
            Q(dt=dt_from - timedelta(1), dttm_work_end__date=dt_from), # чтобы ночные смены попадали
            shop_id=shop.id,
            # child__id__isnull=True,
            is_fact=False,
            is_approved=True,
        )
        emp_cond = Employment.objects.get_active(
            # self.request.user.network_id,
            dt_from=dt_from, dt_to=dt_from, # чтобы не попались трудоустройства с завтрашнего дня
        )
        shop_emp_cond = Employment.objects.get_active(
            self.request.user.network_id,
            dt_from, dt_from, # чтобы не попались трудоустройства с завтрашнего дня
            shop_id=shop.id,
        )
        q = Q(has_wdays=True, has_employments=True)
        if not USERS_WITH_SCHEDULE_ONLY:
            q = q | Q(has_shop_employments=True)
        queryset = WFMUser.objects.all().prefetch_related(
            Prefetch(
                'employees',
                queryset=Employee.objects.annotate(
                    has_wdays=Exists(wd_cond.filter(employee_id=OuterRef('pk'))),
                    has_employments=Exists(emp_cond.filter(employee_id=OuterRef('pk'))),
                    has_shop_employments=Exists(shop_emp_cond.filter(employee_id=OuterRef('pk'))),
                ).filter(q).prefetch_related(
                    Prefetch(
                        'employments',
                        queryset=Employment.objects.get_active_empl_by_priority(
                            None,
                            dt=dt_from,
                            priority_shop_id=shop.id,
                        ).select_related('shop', 'position')
                    )
                )
            ),
            Prefetch(
                'employees__worker_days',
                queryset=WorkerDay.objects.filter(
                    Q(dt=dt_from, dttm_work_start__isnull=False, dttm_work_end__isnull=False) |
                    Q(dt=dt_from - timedelta(1), dttm_work_end__date=dt_from),
                    shop_id=shop.id,
                    is_fact=False,
                    is_approved=True,
                )
            )
        ).annotate(
            has_wdays=Exists(wd_cond.filter(employee__user_id=OuterRef('pk'))),
            has_employments=Exists(emp_cond.filter(employee__user_id=OuterRef('pk'))),
            has_shop_employments=Exists(shop_emp_cond.filter(employee__user_id=OuterRef('pk')))
        ).select_related('network')
        queryset = queryset.filter(q)

        return queryset

    @action(detail=False, methods=['get'])
    def work_shift(self, request, *args, **kwargs):
        filterset = WorkShiftFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        if not Employee.objects.filter(user__username=data.get('worker'), user_id=self.request.user.id).exists():
            raise PermissionDenied()

        wd_kwargs = dict(
            employee__user__username=data.get('worker'),
            dt=data.get('dt'),
            shop__isnull=False,
        )
        if data.get('shop'):
            wd_kwargs['shop__code'] = data.get('shop')
        work_shift = WorkerDay.objects.filter(**wd_kwargs, is_fact=True, is_approved=True).exclude(
            type_id=WorkerDay.TYPE_EMPTY).last()
        if work_shift is None:
            resp_dict = self.request.query_params.dict()
            resp_dict['dttm_work_start'] = None
            resp_dict['dttm_work_end'] = None
            return Response(resp_dict)

        response_serializer = WorkShiftSerializer(instance=work_shift)
        return Response(response_serializer.data)
