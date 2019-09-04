from django import forms
from src.util import forms as util_forms


class WorkerDayApproveForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    year = forms.IntegerField()
    month = forms.IntegerField()


class DeleteWorkerDayApproveForm(forms.Form):
    id = forms.IntegerField()
