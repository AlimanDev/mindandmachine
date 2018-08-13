from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError
from src.util.models_converter import BaseConverter
import json


class GetDepartmentForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class GetSuperShopForm(forms.Form):
    super_shop_id = forms.IntegerField()


class GetSuperShopListForm(forms.Form):
    closed_after_dt = util_forms.DateField(required=False)
    opened_before_dt = util_forms.DateField(required=False)
    min_worker_amount = forms.IntegerField(required=False)
    max_worker_amount = forms.IntegerField(required=False)


class GetSlots(forms.Form):
    user_id = forms.IntegerField(required=True)
    shop_id = forms.IntegerField(required=False)

class GetAllSlots(forms.Form):
    shop_id = forms.IntegerField(required=True)


class SetSlot(forms.Form):
    slots = forms.CharField(required=True)
    user_id = forms.IntegerField()

    def clean_slots(self):
        try:
            value = self.cleaned_data.get('slots')
            if value is None or value == '':
                return None
            value = json.loads(value)
            value = {int(wd): slot_ids for wd, slot_ids in value.items()}
        except:
            raise ValidationError('Invalid data')

        for wd in value:
            if wd < 0 or wd > 6:
                raise ValidationError('Invalid week day')

        return value
