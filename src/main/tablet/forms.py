import datetime
import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms
from src.util.models_converter import PeriodDemandConverter


class GetCashboxesInfo(forms.Form):
    shop_id = forms.IntegerField()

