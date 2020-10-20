import datetime

from django_filters import utils
from django_filters.rest_framework import DjangoFilterBackend

from src.base.models import Employment, Shop


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
            shop = Shop.objects.get(id=shop_id) if shop_id else Shop.objects.get(id=shop_code)
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
        worker_id__in=form.get('worker_id__in')
        worker__username__in=form.get('worker__username__in')


        if not dt_from:
            dt_from = dt if dt else datetime.date.today()
        if not dt_to:
            dt_to = dt if dt else datetime.date.today()
        shop_filter = {}
        if shop_id:
            shop_filter['shop_id'] = shop_id
        ids = Employment.objects.get_active(
            network_id=request.user.network_id,
            dt_from=dt_from, dt_to=dt_to,
            **shop_filter,
        ).values('user_id')

        if worker_id__in:
            ids=ids.filter(
            user_id__in=worker_id__in
            )
        if worker__username__in:
            ids=ids.filter(
            user__username__in=worker__username__in
            )

        # all_employments_for_users = Employment.objects.get_active(dt_from, dt_to).filter(user_id__in=ids)

        return super().filter_queryset(
                request, queryset, view
            ).filter(
                worker_id__in=ids,
                # employment__in=all_employments_for_users\
            ).order_by('worker_id','dt','dttm_work_start')
