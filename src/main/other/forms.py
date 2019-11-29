from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError
import json


class GetSlots(forms.Form):
    user_id = forms.IntegerField(required=True)
    shop_id = forms.IntegerField(required=True)


class GetAllSlots(forms.Form):
    shop_id = forms.IntegerField(required=True)
    work_type_id = forms.IntegerField(required=False)


class UserAllowedFuncsForm(forms.Form):
    worker_id = forms.IntegerField()
