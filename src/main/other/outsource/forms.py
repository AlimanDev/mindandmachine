from src.util import forms as util_forms
from django import forms


class GetOutsourceWorkersForm(forms.Form):
    shop_id = forms.IntegerField()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()


class AddOutsourceWorkersForm(forms.Form):
    shop_id = forms.IntegerField()
    dt = util_forms.DateField()
    from_tm = util_forms.TimeField()
    to_tm = util_forms.TimeField()
    cashbox_type_id = forms.IntegerField()
    amount = forms.IntegerField()
