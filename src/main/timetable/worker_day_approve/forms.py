from django import forms
from src.util import forms as util_forms


class GetWorkerDayApprovesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    dt_from = util_forms.DateField(required=False)
    dt_to = util_forms.DateField(required=False)
    dt_approved = util_forms.DateField(required=False)

class WorkerDayApproveForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    year = forms.IntegerField()
    month = forms.IntegerField()


class DeleteWorkerDayApproveForm(forms.Form):
    id = forms.IntegerField()
