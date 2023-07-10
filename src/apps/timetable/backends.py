import datetime

from django.db.models import Q
from django_filters import utils
from django_filters.rest_framework import DjangoFilterBackend

from src.apps.base.models import Employment, Shop, NetworkConnect


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
        shop_code = request.query_params.get('shop_code')
        if shop_id or shop_code:
            shop = Shop.objects.get(id=shop_id) if shop_id else Shop.objects.get(code=shop_code)
            shop_id = shop.id

        filterset = self.get_filterset(request, queryset, view)

        if filterset is None:
            return queryset

        if not filterset.is_valid() and self.raise_exception:
            raise utils.translate_validation(filterset.errors)

        form = filterset.form.cleaned_data

        dt = form.get('dt')  # | request.data.get('dt')
        dt_from = form.get('dt__gte')  # | request.data.get('dt_from')
        dt_to = form.get('dt__lte')  # | request.data.get('dt_to')
        employee_id__in = form.get('employee_id__in').split(',') if form.get('employee_id__in') else None
        worker__username__in = form.get('worker__username__in')

        if not dt_from:
            dt_from = dt if dt else datetime.date.today()
        if not dt_to:
            dt_to = dt if dt else datetime.date.today()
        shop_filter = {}
        if shop_id:
            shop_filter['shop_id'] = shop_id

        # рефакторинг
        outsourcing_network_qs = list(
            NetworkConnect.objects.filter(
                client=request.user.network_id,
            ).values_list('outsourcing_id', flat=True)
        )
        extra_q = Q(
            Q(
                Q(employee__user__network_id=request.user.network_id) |
                Q(shop__network_id=request.user.network_id)
            ) |
            Q(
                employee__user__network_id__in=outsourcing_network_qs,
                shop__network_id__in=outsourcing_network_qs + [request.user.network_id],
            )
        )
        ids = Employment.objects.get_active(
            extra_q=extra_q,
            dt_from=dt_from, dt_to=dt_to,
            **shop_filter,
        ).values('employee__user_id')

        if employee_id__in:
            ids = ids.filter(
                employee_id__in=employee_id__in
            )
        if worker__username__in:
            ids = ids.filter(
                employee__user__username__in=worker__username__in.split(',')  # TODO: покрыть тестами работу фильтра
            )

        return super().filter_queryset(
            request, queryset, view
        ).filter(
            employee__user__id__in=ids,
        ).order_by('employee__user_id', 'dt', 'dttm_work_start')
