import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetTimeDistributionForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = forms.CharField(required=False)

    def clean_cashbox_type_ids(self):
        value = self.cleaned_data.get('cashbox_type_ids')
        if value is None or value == '':
            return []

        try:
            return json.loads(value)
        except:
            raise ValidationError('invalid cashbox_type_ids')
