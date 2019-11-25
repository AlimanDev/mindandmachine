from django import forms

from src.util import forms as util_forms


class GetIndicatorsForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    type = forms.CharField(max_length=1)
    shop_id = forms.IntegerField()


class GetTimeDistributionForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    work_type_ids = util_forms.IntegersList()
    shop_id = forms.IntegerField()


class ProcessForecastForm(forms.Form):
    shop_id = forms.IntegerField()
