from django import forms
import src.util.forms as util_forms


class GetUserUrvForm(forms.Form):
    worker_id = forms.IntegerField()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
