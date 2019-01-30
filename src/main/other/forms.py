from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError
import json


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


class CreateSlotForm(forms.Form):
    work_type_id = forms.IntegerField()
    tm_start = util_forms.TimeField()
    tm_end = util_forms.TimeField()


class DeleteSlotForm(forms.Form):
    slot_id = forms.IntegerField()
