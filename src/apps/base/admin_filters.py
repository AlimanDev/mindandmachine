from django_admin_listfilter_dropdown.filters import RelatedOnlyDropdownFilter, ChoiceDropdownFilter, RelatedDropdownFilter

class CustomChoiceDropdownFilter(ChoiceDropdownFilter):
    template = 'dropdown_filter.html'

class CustomRelatedOnlyDropdownFilter(RelatedOnlyDropdownFilter):
    template = 'dropdown_filter.html'

class CustomRelatedDropdownFilter(RelatedDropdownFilter):
    template = 'dropdown_filter.html'


class RelatedOnlyDropdownOrderedFilter(CustomRelatedOnlyDropdownFilter):
    ordering_field = None

    def field_choices(self, field, request, model_admin):
        return field.get_choices(include_blank=False, ordering=[self.ordering_field,])

class RelatedOnlyDropdownNameOrderedFilter(RelatedOnlyDropdownOrderedFilter):
    ordering_field = 'name'

class RelatedOnlyDropdownLastNameOrderedFilter(RelatedOnlyDropdownOrderedFilter):
    ordering_field = 'last_name'
