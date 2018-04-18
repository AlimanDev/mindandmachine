from django import forms


class GetDepartmentForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
