from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError


class GetParametersForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class SetParametersForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    queue_length = forms.FloatField()
    idle = forms.IntegerField()
    fot = forms.IntegerField()
    less_norm = forms.IntegerField()
    more_norm = forms.IntegerField()
    tm_shop_opens = util_forms.TimeField()
    tm_shop_closes = util_forms.TimeField()
    shift_start = forms.IntegerField()
    shift_end = forms.IntegerField()
    restricted_start_times = forms.CharField()
    restricted_end_times = forms.CharField()
    min_change_time = forms.IntegerField()
    even_shift_morning_evening = util_forms.BooleanField()
    paired_weekday = util_forms.BooleanField()
    exit1day = util_forms.BooleanField()
    exit42hours = util_forms.BooleanField()
    process_type = util_forms.ChoiceField(choices=['P', 'N'])

    def clean(self):
        if self.errors:
            return

        percent_values = [
            self.cleaned_data['idle'],
            self.cleaned_data['less_norm'],
            self.cleaned_data['more_norm'],
        ]

        for value in percent_values:
            if value > 100 or value < 0:
                raise ValidationError('Значение {} должно быть указано в процентах (0-100)'.format(value))

