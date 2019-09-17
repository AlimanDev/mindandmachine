from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError


class GetWorkersToExchange(forms.Form):
    specialization = forms.IntegerField()  # worktype
    dttm_start = util_forms.DatetimeField()
    dttm_end = util_forms.DatetimeField()

    # from_date = util_forms.DateField()
    # to_date = util_forms.DateField()

    outsource = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = self.cleaned_data


class NotifyWorkersAboutVacancyForm(forms.Form):
    # shop_id = forms.IntegerField()

    work_type = forms.IntegerField()
    dttm_start = util_forms.DatetimeField()
    dttm_end = util_forms.DatetimeField()

    worker_ids = util_forms.IntegersList()


class ShowVacanciesForm(forms.Form):
    shop_id = forms.IntegerField()

    pointer = forms.IntegerField(required=False)
    count = forms.IntegerField(required=False)


class VacancyForm(forms.Form):
    vacancy_id = forms.IntegerField()
