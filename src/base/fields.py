import json

from django import forms
from django.core import checks, exceptions
from django.utils import timezone
from django.db.models import Q, TextField


class CurrentUserNetwork:
    requires_context = True

    def __call__(self, serializer_field):
        if not serializer_field.context['request']:   # for schema generation metadata
            return 1
        return serializer_field.context['request'].user.network_id



class UserworkShop:
    requires_context = True

    def __call__(self, serializer_field):
        if not serializer_field.context['request']:   # for schema generation metadata
            return 1
        from src.base.models import Employment
        now_day = timezone.now().date()
        employment =  Employment.objects.filter(
            Q(dt_fired__gte=now_day) | Q(dt_fired__isnull=True),
            employee__user_id=serializer_field.context['request'].user.id,
        ).first()
        return employment.shop_id if employment else None

class MultipleChoiceField(TextField):

    def __init__(self, *args, **kwargs):
        kwargs['default'] = "[]"
        kwargs['max_length'] = None
        super().__init__(*args, **kwargs)

    def check(self, **kwargs):
        return [
            *super().check(**kwargs),
            *self._check_choices_set(),
        ]


    def _check_choices_set(self):
        if not self.choices:
            return [
                checks.Error(
                    "'choices' must have at least 1 element.",
                    obj=self,
                )
            ]
        return []

    def to_python(self, value):
        if value is None:
            return []
        if isinstance(value, (list, set, tuple)):
            return list(value)
        return json.loads(value)

    def formfield(self, **kwargs):
        return super().formfield(choices_form_class=forms.TypedMultipleChoiceField, coerce=self.check_value_in_choices, **kwargs)
    
    def check_value_in_choices(self, value):
        if not value in list(map(lambda x: x[0], self.choices)):
            raise exceptions.ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'value': value},
            )

        return value

    def validate(self, value, model_instance):
        if not self.editable:
            # Skip validation for non-editable fields.
            return

        if value not in self.empty_values:
            for val in value:
                self.check_value_in_choices(val)

        if value is None and not self.null:
            raise exceptions.ValidationError(self.error_messages['null'], code='null')

        if not self.blank and value in self.empty_values:
            raise exceptions.ValidationError(self.error_messages['blank'], code='blank')

    def value_from_object(self, obj):
        return self.to_python(getattr(obj, self.attname))

    def get_db_prep_save(self, value, connection):
        value = self.get_db_prep_value(value, connection=connection, prepared=False)
        if not isinstance(value, str):
            value = json.dumps(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return self.to_python(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return []
        return self.to_python(value)
