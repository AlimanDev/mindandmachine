from django import forms
from src.util import forms as util_forms


class GetWorkersToExchange(forms.Form):
    specialization = forms.IntegerField(required=True)
    dttm = util_forms.DatetimeField(required=True)
    shop_id = forms.IntegerField(required=False)




