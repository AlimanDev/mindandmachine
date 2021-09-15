import distutils.util

from django.db.models import Q, Exists, OuterRef
from django_filters import utils
from django_filters.rest_framework import DjangoFilterBackend

from src.base.models import Employee, Employment


class EmployeeFilterBackend(DjangoFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if view.detail:
            return super().filter_queryset(request, queryset, view)

        filterset = self.get_filterset(request, queryset, view)
        if filterset is None:
            return queryset

        if not filterset.is_valid() and self.raise_exception:
            raise utils.translate_validation(filterset.errors)

        other_deps_employees_with_wd_in_curr_shop = request.query_params.get(
            'other_deps_employees_with_wd_in_curr_shop')
        if other_deps_employees_with_wd_in_curr_shop and bool(
                distutils.util.strtobool(other_deps_employees_with_wd_in_curr_shop)):
            shop_id = filterset.form.cleaned_data.get('shop_id')
            dt_from = filterset.form.cleaned_data.get('employments__dt_from')
            dt_to = filterset.form.cleaned_data.get('employments__dt_to')

            if shop_id and dt_from and dt_to:
                has_shop_employment_sq = Exists(
                    Employment.objects.get_active(
                        employee_id=OuterRef('id'),
                        dt_from=dt_from,
                        dt_to=dt_to,
                        shop_id=shop_id,
                    )
                )

                other_deps_employees_with_wd_in_curr_shop_qs = Employee.objects.annotate(
                    has_shop_employment=has_shop_employment_sq,
                ).filter(
                    has_shop_employment=False,
                    worker_days__shop_id=shop_id,
                )
                return Employee.objects.filter(
                    Q(id__in=filterset.qs.values_list('id', flat=True)) |
                    Q(id__in=other_deps_employees_with_wd_in_curr_shop_qs.values_list('id', flat=True)),
                ).annotate(
                    has_shop_employment=has_shop_employment_sq,
                )

        return filterset.qs
