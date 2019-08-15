from django import forms
from src.util import forms as util_forms
from django.core.exceptions import ValidationError


class GetDepartmentForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class GetSuperShopForm(forms.Form):
    super_shop_id = forms.IntegerField()


class GetSuperShopListForm(forms.Form):
    pointer = forms.IntegerField()
    items_per_page = forms.IntegerField()
    title = forms.CharField(required=False, max_length=256)
    # super_shop_type = util_forms.ChoiceField([SuperShop.TYPE_COMMON, SuperShop.TYPE_HYPERMARKET], '')
    region = forms.CharField(required=False, max_length=256)
    closed_before_dt = util_forms.DateField(required=False)
    opened_after_dt = util_forms.DateField(required=False)
    fot_revenue = util_forms.RangeField(required=False)
    revenue = util_forms.RangeField(required=False)
    lack = util_forms.RangeField(required=False)
    fot = util_forms.RangeField(required=False)
    idle = util_forms.RangeField(required=False)
    workers_amount = util_forms.RangeField(required=False)
    sort_type = forms.CharField(required=False)
    format = forms.CharField()

    def clean(self):
        available_formats = ('raw', 'excel', )
        if self.cleaned_data['format'] not in available_formats:
            raise ValidationError('unknown format')


class AddEditSuperShopForm(forms.Form):
    title = forms.CharField(max_length=128)
    code = forms.CharField(max_length=64)
    address = forms.CharField(max_length=256, required=False)
    region = forms.CharField(required=False)
    tm_start = util_forms.TimeField()
    tm_end = util_forms.TimeField()

    class Meta:
        abstract = True


class AddSuperShopForm(AddEditSuperShopForm):
    open_dt = util_forms.DateField()


class EditSuperShopForm(AddEditSuperShopForm):
    supershop_id = forms.IntegerField()
    close_dt = util_forms.DateField(required=False)


class AddEditShopForm(forms.Form):
    title = forms.CharField(max_length=64)
    tm_shop_opens = util_forms.TimeField()
    tm_shop_closes = util_forms.TimeField()


class AddShopForm(AddEditShopForm):
    super_shop_id = forms.IntegerField()


class EditShopForm(AddEditShopForm):
    shop_id = forms.IntegerField()
    to_delete = util_forms.BooleanField(required=False)


class GetParametersForm(forms.Form):
    shop_id = forms.IntegerField(required=False)


class SetParametersForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    queue_length = forms.FloatField()
    idle = forms.IntegerField()
    fot = forms.IntegerField()
    less_norm = forms.IntegerField()
    more_norm = forms.IntegerField()
    tm_shop_opens = util_forms.TimeField()
    tm_shop_closes = util_forms.TimeField()
    shift_start = forms.IntegerField()
    shift_end = forms.IntegerField()
    restricted_start_times = forms.CharField()
    restricted_end_times = forms.CharField()
    min_change_time = forms.IntegerField()
    absenteeism = forms.IntegerField()
    even_shift_morning_evening = util_forms.BooleanField()
    # workdays_holidays_same = util_forms.BooleanField() TODO(as)
    paired_weekday = util_forms.BooleanField()
    exit1day = util_forms.BooleanField()
    exit42hours = util_forms.BooleanField()
    process_type = util_forms.ChoiceField(choices=['P', 'N'])

    def clean(self):
        if self.errors:
            return

        percent_values = [
            self.cleaned_data['idle'],
            self.cleaned_data['less_norm'],
            self.cleaned_data['more_norm'],
            self.cleaned_data['absenteeism'],
        ]

        for value in percent_values:
            if value > 100 or value < 0:
                raise ValidationError('Значение {} должно быть указано в процентах (0-100)'.format(value))


class GetSuperShopStatsForm(forms.Form):
    supershop_id = forms.IntegerField()
