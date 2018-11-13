import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetIndicatorsForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    type = forms.CharField(max_length=1)
    shop_id = forms.IntegerField(required=False)


class GetTimeDistributionForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = util_forms.IntegersList()
    shop_id = forms.IntegerField(required=False)


class GetParametersForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class SetParametersForm(forms.Form):
    shop_id = forms.IntegerField()
    mean_queue_length = forms.FloatField()
    max_queue_length = forms.FloatField()
    dead_time_part = forms.FloatField()
