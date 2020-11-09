import logging
from datetime import timedelta

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

from src.base.models import (
    Employment,
    User as WFMUser
)
from src.recognition.authentication import TickPointTokenAuthentication
from src.recognition.wfm.serializers import WorkerDaySerializer, WorkShiftSerializer
from src.timetable.models import WorkerDay

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

    serializer_class = WorkerDaySerializer
    # search_fields = ['first_name', 'last_name']
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    def get_authenticators(self):
        if settings.USER_TOKEN_AUTH:
            return [TokenAuthentication()]
        else:
            return [TickPointTokenAuthentication()]

    # filterset_class = WorkerDayFilterSet
    def get_queryset(self):
        tick_point = self.request.user

        dt_from = now().replace(hour=0, minute=0, second=0)
        dt_to = dt_from + timedelta(days=1)

        wd_cond = WorkerDay.objects.filter(
            worker_id=OuterRef('pk'),
            shop_id=tick_point.shop_id,
            dttm_work_start__gte=dt_from,
            dttm_work_end__lte=dt_to,
            child__id__isnull=True
        )
        emp_cond = Employment.objects.get_active(
            self.request.user.network_id,
            dt_from, dt_to,
            user_id=OuterRef('pk'),
        )
        shop_emp_cond = Employment.objects.get_active(
            self.request.user.network_id,
            dt_from, dt_to,
            user_id=OuterRef('pk'),
            shop_id=tick_point.shop_id,
        )

        queryset = WFMUser.objects.all().prefetch_related(
            Prefetch('worker_day',
                     queryset=WorkerDay.objects.filter(
                         shop_id=tick_point.shop_id,
                         dttm_work_start__gte=dt_from,
                         dttm_work_end__lte=dt_to,
                         child__id__isnull=True,
                     )
                     )
        ).annotate(
            has_wdays=Exists(wd_cond),
            has_employments=Exists(emp_cond),
            has_shop_employments=Exists(shop_emp_cond)
        )
        q = Q(has_wdays=True, has_employments=True)
        if not USERS_WITH_SCHEDULE_ONLY:
            q = q | Q(has_shop_employments=True)
        queryset = queryset.filter(q)

        return queryset

    @action(detail=False, methods=['get'])
    def work_shift(self, request, *args, **kwargs):
        query_params_serializer = WorkShiftSerializer(data=self.request.query_params)
        query_params_serializer.is_valid(raise_exception=True)
        work_shift = WorkerDay.objects.filter(
            **query_params_serializer.validated_data,
            is_fact=True, is_approved=True,
        ).last()
        if work_shift is None:
            resp_dict = self.request.query_params.dict()
            resp_dict['dttm_work_start'] = None
            resp_dict['dttm_work_end'] = None
            return Response(resp_dict)

        response_serializer = WorkShiftSerializer(instance=work_shift)
        return Response(response_serializer.data)
