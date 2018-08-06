from src.util import forms as util_forms
from django import forms


class SetNotificationsReadForm(forms.Form):
    ids = util_forms.IntegersList(required=True)
