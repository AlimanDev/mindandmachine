import distutils.util

from django.db.models import Exists, OuterRef, Q, BooleanField, ExpressionWrapper, F
from django.db.models.query import Prefetch
from django.utils import timezone
from django_filters import utils
from django_filters.rest_framework import DjangoFilterBackend

from src.base.models import Employee, Employment, Shop, User
from src.timetable.models import WorkerDay


class EmployeeFilterBackend(DjangoFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if view.detail:
            return super().filter_queryset(request, queryset, view)

        filterset = self.get_filterset(request, queryset, view)
        if filterset is None:
            return queryset

        if not filterset.is_valid() and self.raise_exception:
            raise utils.translate_validation(filterset.errors)

        qs = filterset.qs
        other_deps_employees_with_wd_in_curr_shop = request.query_params.get(
            'other_deps_employees_with_wd_in_curr_shop')
        shop_id = filterset.form.cleaned_data.get('shop_id')
        dt_now = timezone.now().date()
        dt_from = filterset.form.cleaned_data.get('employments__dt_from') or dt_now
        dt_to = filterset.form.cleaned_data.get('employments__dt_to') or dt_now
        if shop_id:
            has_shop_employment_sq = Exists(
                Employment.objects.get_active(
                    employee_id=OuterRef('id'),
                    dt_from=dt_from,
                    dt_to=dt_to,
                    shop_id=shop_id,
                )
            )
        if other_deps_employees_with_wd_in_curr_shop and bool(
                distutils.util.strtobool(other_deps_employees_with_wd_in_curr_shop)):
            if shop_id:
                other_deps_employees_with_wd_in_curr_shop_qs = Employee.objects.filter(
                    Exists(
                        WorkerDay.objects.filter(
                            employee_id=OuterRef('id'),
                            dt__gte=dt_from,
                            dt__lte=dt_to,
                            shop_id=shop_id,
                            type__is_dayoff=False,
                        )
                    ),
                    ~has_shop_employment_sq,
                )
                qs = Employee.objects.filter(
                    Q(id__in=filterset.qs.values_list('id', flat=True)) |
                    Q(id__in=other_deps_employees_with_wd_in_curr_shop_qs.values_list('id', flat=True)),
                    employments__dttm_deleted__isnull=True,
                ).prefetch_related(
                    Prefetch(
                        'user',
                        queryset=User.objects.all().annotate(
                            userconnecter_id=F('userconnecter'),
                        ),
                        to_attr='employee_user',
                    )
                )

            shop = Shop.objects.get(pk=shop_id) if shop_id else request.user.get_shops().first()
            qs = qs.annotate(
                from_another_network=ExpressionWrapper(
                    ~Q(user__network_id=shop.network_id),
                    output_field=BooleanField(),
                )
            )

        employee_id = filterset.form.cleaned_data.get('id')
        if employee_id:
            qs = qs.filter(
                id=employee_id,
            )

        if shop_id:
            qs = qs.annotate(
                has_shop_employment=has_shop_employment_sq,
            )
        return qs.distinct()
