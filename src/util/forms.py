from django import forms


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
    def __init__(self, choices, **kwargs):
        super().__init__(
            choices=((x, '') for x in choices),
            **kwargs
        )
