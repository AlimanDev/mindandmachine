from django import forms
from src.util import forms as util_forms


class GetTypesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class GetCashboxesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    from_dt = util_forms.DateField(required=False)
    to_dt = util_forms.DateField(required=False)
    cashbox_type_ids = util_forms.IntegersList()


class CreateCashboxForm(forms.Form):
    cashbox_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)


class DeleteCashboxForm(forms.Form):
    shop_id = forms.IntegerField()
    cashbox_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)
    bio = forms.CharField(max_length=512)


class UpdateCashboxForm(forms.Form):
    from_cashbox_type_id = forms.IntegerField()
    to_cashbox_type_id = forms.IntegerField()
    number = forms.CharField(max_length=6)


class CreateCashboxTypeForm(forms.Form):
    shop_id = forms.IntegerField()
    name = forms.CharField(max_length=128)
    is_main_type = forms.BooleanField(required=False)


class DeleteCashboxTypeForm(forms.Form):
    cashbox_type_id = forms.IntegerField()


class CashboxesOpenTime(forms.Form):
    shop_id = forms.IntegerField(required=False)
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()


class CashboxesUsedResource(forms.Form):
    shop_id = forms.IntegerField(required=False)
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()


