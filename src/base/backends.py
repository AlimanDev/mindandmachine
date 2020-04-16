from django_filters.rest_framework import DjangoFilterBackend

from src.base.filters import EmploymentFilter, EmploymentRequiredFilter
class EmploymentFilterBackend(DjangoFilterBackend):
    def get_filterset_class(self, view, queryset=None):
        if view.action == 'month_stat':
            return EmploymentRequiredFilter
        else:
            return EmploymentFilter