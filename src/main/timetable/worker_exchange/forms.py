from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError


class GetWorkersToExchange(forms.Form):
    # super_shop_id = forms.IntegerField()

    specialization = forms.IntegerField()  # worktype
    dttm_start = util_forms.DatetimeField()
    dttm_end = util_forms.DatetimeField()

    # from_date = util_forms.DateField()
    # to_date = util_forms.DateField()

    own_shop = forms.BooleanField(required=False)
    other_shops = forms.BooleanField(required=False)
    other_supershops = forms.BooleanField(required=False)
    outsource = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = self.cleaned_data

        if not cleaned_data['own_shop'] and not cleaned_data['other_shops']\
                and not cleaned_data['other_supershops'] and not cleaned_data['outsource']:
            raise ValidationError('Выберите хотя бы одну из опций поиска по магазинам')


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

