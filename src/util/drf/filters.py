from django.db.models import Q
from django_filters import Filter, CharFilter, NumberFilter, BooleanFilter, DateFilter
from django_filters.constants import EMPTY_VALUES


class QFilterAndOrIsNullMixin(Filter):
    def __init__(self, *args, or_isnull=False, **kwargs):
        self.or_isnull = or_isnull
        super(QFilterAndOrIsNullMixin, self).__init__(*args, **kwargs)

    def get_q(self, value):
        if value in EMPTY_VALUES:
            return None

        lookup = '%s__%s' % (self.field_name, self.lookup_expr)
        q = Q(**{lookup: value})
        if self.or_isnull:
            isnull_lookup = '%s__%s' % (self.field_name, 'isnull')
            q |= Q(**{isnull_lookup: True})
        return q


class ListFilter(Filter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        value_list = value.split(",")
        qs = super().filter(qs, value_list)
        return qs


class QListFilter(QFilterAndOrIsNullMixin, ListFilter):
    def get_q(self, value):
        if value in EMPTY_VALUES:
            return None

        value_list = value.split(",")
        q = super().get_q(value_list)
        return q


class QCharFilter(QFilterAndOrIsNullMixin, CharFilter):
    pass


class QBooleanFilter(QFilterAndOrIsNullMixin, BooleanFilter):
    pass


class QNumberFilter(QFilterAndOrIsNullMixin, NumberFilter):
    pass


class QDateFilter(QFilterAndOrIsNullMixin, DateFilter):
    pass
