from src.util import forms as util_forms
from django import forms


class SetNotificationsReadForm(forms.Form):
    ids = util_forms.IntegersList(required=True)
    set_all = forms.BooleanField(required=False, initial=False)


class GetNotificationsForm(forms.Form):
    pointer = forms.IntegerField(required=False)
    count = forms.IntegerField(required=False)
    type = util_forms.ChoiceField(['all', 'vacancy', 'other'], default='all')

    shop_id = forms.IntegerField(required=False)
    dt = util_forms.DateField(required=False)


class NotifyAction(forms.Form):
    notify_id = forms.IntegerField(required=True)
