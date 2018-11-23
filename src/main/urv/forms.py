from django import forms
import src.util.forms as util_forms


class GetUserUrvForm(forms.Form):
    worker_ids = util_forms.IntegersList()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
