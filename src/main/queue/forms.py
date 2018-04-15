import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms


class GetIndicatorsForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    type = util_forms.PeriodDemandForecastType()


class GetTimeDistributionForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    cashbox_type_ids = util_forms.CashboxTypeIds()
