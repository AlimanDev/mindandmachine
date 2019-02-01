import datetime

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetIndicatorsForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    work_type_id = forms.IntegerField(required=False)
    shop_id = forms.IntegerField(required=False)


class GetForecastForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    operation_type_ids = util_forms.IntegersList()
    format = util_forms.ChoiceField(choices=['raw', 'excel'], default='raw')
    shop_id = forms.IntegerField(required=False)


class SetDemandForm(forms.Form):
    from_dttm = util_forms.DatetimeField()
    to_dttm = util_forms.DatetimeField()
    work_type_id = util_forms.IntegersList()
    multiply_coef = forms.FloatField(required=False)
    set_value = forms.FloatField(required=False)
    shop_id = forms.IntegerField()

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['from_dttm'] > self.cleaned_data['to_dttm']:
            raise ValidationError('дата начала не может быть больше даты окончания')

        if self.cleaned_data['from_dttm'].date() < datetime.date.today():
            raise ValidationError('невозможно изменять спрос за предыдущий период')

        m_exists = self.cleaned_data.get('multiply_coef') is not None
        v_exists = self.cleaned_data.get('set_value') is not None
        if m_exists and v_exists:
            raise ValidationError('cannot exist both coef and value')

        if not m_exists and not v_exists:
            raise ValidationError('multiply or value have to be')


class GetDemandChangeLogsForm(forms.Form):
    work_type_id = forms.IntegerField()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    shop_id = forms.IntegerField()


class GetVisitorsInfoForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    shop_id = forms.IntegerField()


class CreatePredictBillsRequestForm(forms.Form):
    shop_id = forms.IntegerField()
    dt = util_forms.DateField()

