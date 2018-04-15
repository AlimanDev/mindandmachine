import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetCashiersTimetableForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = util_forms.CashboxTypeIds()
    format = util_forms.ChoiceField(['raw', 'excel'], default='raw')

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['from_dt'] > self.cleaned_data['to_dt']:
            raise forms.ValidationError('dt_from have to be less or equal than dt_to')


class GetWorkersForm(forms.Form):
    from_dttm = util_forms.DatetimeField()
    to_dttm = util_forms.DatetimeField()
    cashbox_type_ids = util_forms.CashboxTypeIds()

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['from_dttm'] > self.cleaned_data['to_dttm']:
            raise forms.ValidationError('dttm_from have to be less or equal than dttm_to')
