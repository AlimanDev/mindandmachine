from django import forms
from src.util import forms as util_forms


class GetDepartmentForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class GetSuperShopForm(forms.Form):
    super_shop_id = forms.IntegerField()


class GetSuperShopListForm(forms.Form):
    closed_after_dt = util_forms.DateField(required=False)
    opened_before_dt = util_forms.DateField(required=False)
    min_worker_amount = forms.IntegerField(required=False)
    max_worker_amount = forms.IntegerField(required=False)


class GetNotificationsForm(forms.Form):
    pass
