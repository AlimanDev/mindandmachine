import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetTypesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class GetCashboxesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    from_dt = util_forms.DateField(required=False)
    to_dt = util_forms.DateField(required=False)
    cashbox_type_ids = forms.CharField(required=False)

    def clean_cashbox_type_ids(self):
        value = self.cleaned_data.get('cashbox_type_ids')
        if value is None or value == '':
            return []

        try:
            return json.loads(value)
        except:
            raise ValidationError('invalid cashbox_type_ids')


class CreateCashboxForm(forms.Form):
    cashbox_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)


class DeleteCashboxForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    number = forms.CharField(max_length=6)
    bio = forms.CharField(max_length=512)


class UpdateCashboxForm(forms.Form):
    from_cashbox_type_id = forms.IntegerField()
    to_cashbox_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)
