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
    worker_ids = util_forms.IntegersList(required=True)
    shop_id = forms.IntegerField()


class CreateTimetableForm(forms.Form):
    shop_id = forms.IntegerField()
    dt = util_forms.DateField()

    def clean_dt(self):
        dt = self.cleaned_data['dt']
        return datetime.date(year=dt.year, month=dt.month, day=1)


class DeleteTimetableForm(forms.Form):
    shop_id = forms.IntegerField()
    dt = util_forms.DateField()

    def clean_dt(self):
        dt = self.cleaned_data['dt']
        return datetime.date(year=dt.year, month=dt.month, day=1)


class SetTimetableForm(forms.Form):
    data = forms.CharField()
