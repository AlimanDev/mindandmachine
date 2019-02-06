from django import forms
from src.util import forms as util_forms


class GetTable(forms.Form):
    shop_id = forms.IntegerField(required=False)
    weekday = util_forms.DateField()
    checkpoint = forms.IntegerField(required=False)
    inspection_version = forms.BooleanField(required=False)


class GetDemandXlsxForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    shop_id = forms.IntegerField()
    demand_model = forms.CharField(max_length=1)


class GetUrvXlsxForm(forms.Form):
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    shop_id = forms.IntegerField()
