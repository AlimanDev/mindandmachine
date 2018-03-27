from django import forms
from src.util import forms as util_forms


class GetTypesForm(forms.Form):
    shop_id = forms.IntegerField()
    full = util_forms.BooleanField()
