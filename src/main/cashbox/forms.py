from django import forms
from src.util import forms as util_forms


class GetTypesForm(forms.Form):
    shop_id = forms.IntegerField()


class GetCashboxesForm(forms.Form):
    shop_id = forms.IntegerField()
    from_dt = util_forms.DateField(required=False)
    to_dt = util_forms.DateField(required=False)
    work_type_ids = util_forms.IntegersList()


class CreateCashboxForm(forms.Form):
    work_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)


class DeleteCashboxForm(forms.Form):
    shop_id = forms.IntegerField()
    work_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)
    bio = forms.CharField(max_length=512)


class UpdateCashboxForm(forms.Form):
    from_work_type_id = forms.IntegerField()
    to_work_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)


class CreateWorkTypeForm(forms.Form):
    shop_id = forms.IntegerField()
    name = forms.CharField(max_length=128)


class DeleteWorkTypeForm(forms.Form):
    work_type_id = forms.IntegerField()


class EditWorkTypeForm(forms.Form):
    work_type_id = forms.IntegerField()
    workers_amount = util_forms.RangeField(required=False)
    new_title = forms.CharField(required=False, max_length=128)
    operation_types = forms.CharField(max_length=8096)
    slots = forms.CharField(max_length=8096)


class CashboxesOpenTime(forms.Form):
    shop_id = forms.IntegerField()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()


class CashboxesUsedResource(forms.Form):
    shop_id = forms.IntegerField(required=False)
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()


