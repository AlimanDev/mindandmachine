from django import forms
from django.core.exceptions import ValidationError


class DateField(forms.DateField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=('%d.%m.%Y',),
            **kwargs
        )


class TimeField(forms.TimeField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=('%H:%M:%S',),
            **kwargs
        )


class DatetimeField(forms.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=('%H:%M:%S %d.%m.%Y',),
            **kwargs
        )


class ChoiceField(forms.ChoiceField):
    def __init__(self, choices, default=None, **kwargs):
        self.default = default
        if default is not None:
            kwargs['required'] = False

        super().__init__(
            choices=((x, '') for x in choices),
            **kwargs
        )

    def clean(self, value):
        result = super().clean(value)
        if result is None and self.default is not None:
            result = self.default
        return result


class MultipleChoiceField(forms.MultipleChoiceField):
    def __init__(self, choices, default=None, **kwargs):
        self.default = default
        if default is not None:
            kwargs['required'] = False

        super().__init__(
            choices=((x, '') for x in choices),
            **kwargs
        )

    def to_python(self, value):
        value = super().to_python(value)
        result = []
        for x in value:
            result += x.split(',')
        return result

    def clean(self, value):
        value = super().clean(value)
        if value is None and self.default is not None:
            value = self.default
        return value


class BooleanField(forms.BooleanField):
    def __init__(self):
        super().__init__(required=False)
