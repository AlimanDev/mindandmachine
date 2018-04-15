import datetime
import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms
from src.util.models_converter import PeriodDemandConverter


class GetIndicatorsForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    type = util_forms.PeriodDemandForecastType()


class GetForecastForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = util_forms.CashboxTypeIds()
    format = util_forms.ChoiceField(choices=['raw', 'excel'], default='raw')
    # data_type = forms.CharField()

    # def clean_data_type(self):
    #     value = self.cleaned_data.get('data_type')
    #     if value is None or value == '':
    #         raise ValidationError('Invalid enum value')
    #
    #     try:
    #         value = [PeriodDemandConverter.parse_forecast_type(v) for v in json.loads(value)]
    #     except:
    #         raise ValidationError('Invalid enum value')
    #
    #     if None in value:
    #         raise ValidationError('Invalid enum value')
    #
    #     return value


class SetDemandForm(forms.Form):
    from_dttm = util_forms.DatetimeField()
    to_dttm = util_forms.DatetimeField()
    cashbox_type_ids = util_forms.CashboxTypeIds()
    multiply_coef = forms.FloatField(required=False)
    set_value = forms.FloatField(required=False)

    def clean(self):
        if self.cleaned_data['from_dttm'] > self.cleaned_data['to_dttm']:
            raise ValidationError('cannot from_dt be gt to_dt')

        if self.cleaned_data['from_dttm'] < datetime.datetime.now():
            raise ValidationError('cannot change past data')

        m_exists = 'multiply_coef' in self.cleaned_data
        v_exists = 'set_value' in self.cleaned_data
        if m_exists and v_exists:
            raise ValidationError('cannot exist both coef and value')

        if not m_exists and not v_exists:
            raise ValidationError('multiply or value have to be')
