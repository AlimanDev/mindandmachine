import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms
from src.util.models_converter import PeriodDemandConverter


class GetForecastForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = forms.CharField(required=False)
    format = util_forms.ChoiceField(choices=['raw', 'excel'], default='raw')
    data_type = forms.CharField()

    def clean_cashbox_type_ids(self):
        value = self.cleaned_data.get('cashbox_type_ids')
        if value is None or value == '':
            return []

        try:
            return json.loads(value)
        except:
            raise ValidationError('invalid cashbox_type_ids')

    def clean_data_type(self):
        value = self.cleaned_data.get('data_type')
        if value is None or value == '':
            raise ValidationError('Invalid enum value')

        try:
            value = [PeriodDemandConverter.parse_forecast_type(v) for v in json.loads(value)]
        except:
            raise ValidationError('Invalid enum value')

        if None in value:
            raise ValidationError('Invalid enum value')

        return value


class SetDemandForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = forms.CharField(required=False)
