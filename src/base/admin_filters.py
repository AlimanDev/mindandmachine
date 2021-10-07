from django_admin_listfilter_dropdown.filters import RelatedOnlyDropdownFilter, ChoiceDropdownFilter

class CustomChoiceDropdownFilter(ChoiceDropdownFilter):
    template = 'dropdown_filter.html'

class CustomRelatedOnlyDropdownFilter(RelatedOnlyDropdownFilter):
    template = 'dropdown_filter.html'

class RelatedOnlyDropdownOrderedFilter(CustomRelatedOnlyDropdownFilter):
    ordering_field = None

    def field_choices(self, field, request, model_admin):
        pk_qs = model_admin.get_queryset(request).distinct().values_list('%s__pk' % self.field_path, flat=True)
        return field.get_choices(include_blank=False, limit_choices_to={'pk__in': pk_qs}, ordering=[self.ordering_field,])


class RelatedOnlyDropdownNameOrderedFilter(RelatedOnlyDropdownOrderedFilter):
    ordering_field = 'name'


class RelatedOnlyDropdownLastNameOrderedFilter(RelatedOnlyDropdownOrderedFilter):
    ordering_field = 'last_name'
