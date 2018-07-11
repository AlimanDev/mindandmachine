import datetime
import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms
from src.util.models_converter import PeriodDemandConverter


class GetCashboxesInfo(forms.Form):
    shop_id = forms.IntegerField()


class GetCashiersInfo(forms.Form):
    shop_id = forms.IntegerField()
    dttm = util_forms.DatetimeField()


class ChangeCashierStatus(forms.Form):
    worker_id = forms.IntegerField()
    status = forms.CharField()
    cashbox_id = forms.IntegerField(required=False)
    change_time = forms.DateTimeField(widget=forms.TimeInput('%M/%d %H:%M'), required=False)
