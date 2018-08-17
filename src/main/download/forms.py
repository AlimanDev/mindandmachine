from django import forms
from src.util import forms as util_forms


class GetTable(forms.Form):
    shop_id = forms.IntegerField(required=False)
    weekday = util_forms.DateField()
