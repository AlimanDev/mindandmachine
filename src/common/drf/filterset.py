from django.db.models import Q
from django_filters.rest_framework import FilterSet


class QFilterSet(FilterSet):
    """
    Нужен для того, чтобы запросы по длинному лукапу (field__other_field__another_field)
    выполнялись внутри одного filter.

    Иначе фильтры с подобными лукапами работают не совсем корректно.
    """

    def filter_queryset(self, queryset):
        initial_q = Q()
        for name, value in self.form.cleaned_data.items():
            q = self.filters[name].get_q(value)
            if q is not None:
                assert isinstance(q, Q), \
                    "Expected '%s.%s' to return a Q, but got a %s instead." \
                    % (type(self).__name__, name, type(q).__name__)
                initial_q &= q
        return queryset.filter(initial_q)
