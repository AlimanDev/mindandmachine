import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetWorkersForm(forms.Form):
    dttm_from = util_forms.DatetimeField()
    dttm_to = util_forms.DatetimeField()
    cashbox_type_ids = forms.CharField(required=False)

    def clean_cashbox_type_ids(self):
        value = self.cleaned_data.get('cashbox_type_ids')
        if value is None or value == '':
            return []

        try:
            return json.loads(value)
        except:
            raise ValidationError('Invalid data')

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data["dttm_from"] > self.cleaned_data["dttm_to"]:
            raise forms.ValidationError('dttm_from have to be less or equal than dttm_to')
