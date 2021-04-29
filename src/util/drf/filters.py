from django.db.models import Q
from django_filters import Filter, CharFilter, NumberFilter, BooleanFilter, DateFilter
from django_filters.constants import EMPTY_VALUES


class QFilterMixin(Filter):
    def get_q(self, value):
        if value in EMPTY_VALUES:
            return None

        lookup = '%s__%s' % (self.field_name, self.lookup_expr)
        return Q(**{lookup: value})


class ListFilter(Filter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        value_list = value.split(",")
        qs = super().filter(qs, value_list)
        return qs


class QListFilter(QFilterMixin, ListFilter):
    def get_q(self, value):
        if value in EMPTY_VALUES:
            return None

        value_list = value.split(",")
        q = super().get_q(value_list)
        return q


class QCharFilter(QFilterMixin, CharFilter):
    pass


class QBooleanFilter(QFilterMixin, BooleanFilter):
    pass


class QNumberFilter(QFilterMixin, NumberFilter):
    pass


class QDateFilter(QFilterMixin, DateFilter):
    pass
