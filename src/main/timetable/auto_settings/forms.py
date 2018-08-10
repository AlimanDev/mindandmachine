import datetime

from django import forms

from src.util import forms as util_forms


class GetStatusForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    dt = util_forms.DateField()

    def clean_dt(self):
        dt = self.cleaned_data['dt']
        return datetime.date(year=dt.year, month=dt.month, day=1)


class SetSelectedCashiersForm(forms.Form):
    cashier_ids = util_forms.IntegersList(required=True)
    value = util_forms.BooleanField(required=True)


class CreateTimetableForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    dt = util_forms.DateField()

    def clean_dt(self):
        dt = self.cleaned_data['dt']
        return datetime.date(year=dt.year, month=dt.month, day=1)


class DeleteTimetableForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    dt = util_forms.DateField()

    def clean_dt(self):
        dt = self.cleaned_data['dt']
        return datetime.date(year=dt.year, month=dt.month, day=1)


class SetTimetableForm(forms.Form):
    key = forms.CharField()
    data = forms.CharField()


class CreatePredictBillsRequestForm(forms.Form):
    shop_id = forms.IntegerField()
    dt = util_forms.DateField()
