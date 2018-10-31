import json
from datetime import datetime, timedelta

from django import forms
from django.core.exceptions import ValidationError

from src.db.models import WorkerDay, User
from src.util import forms as util_forms
from src.util.models_converter import WorkerDayConverter, UserConverter, BaseConverter


class GetCashiersListForm(forms.Form):
    dt_hired_before = util_forms.DateField(required=False)
    dt_fired_after = util_forms.DateField(required=False)
    shop_id = forms.IntegerField(required=False)
    consider_outsource = forms.BooleanField(required=False)

    def clean_dt_hired_before(self):
        value = self.cleaned_data.get('dt_hired_before')
        if value is None:
            return (datetime.now() + timedelta(days=10)).date()
        return value

    def clean_dt_fired_after(self):
        value = self.cleaned_data.get('dt_fired_after')
        if value is None:
            return datetime.now().date()
        return value


class GetCashierTimetableForm(forms.Form):
    worker_id = util_forms.IntegersList(required=True)
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    format = util_forms.ChoiceField(['raw', 'excel'], 'raw')
    shop_id = forms.IntegerField()
    checkpoint = forms.IntegerField(required=False)

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['from_dt'] > self.cleaned_data['to_dt']:
            raise forms.ValidationError('from_dt have to be less or equal than to_dt')


class DublicateCashierTimetableForm(forms.Form):
    from_worker_id = forms.IntegerField(required=True)
    to_worker_id = forms.IntegerField(required=True)
    from_dt = util_forms.DateField(required=True)
    to_dt = util_forms.DateField(required=True)

    def clean_from_worker_id(self):
        try:
            main_worker = User.objects.get(id=self.cleaned_data['from_worker_id'])
        except User.DoesNotExist:
            raise forms.ValidationError('Неверно указан сотрудник, чье расписание копировать.')
        return main_worker.id

    def clean_to_worker_id(self):
        try:
            trainee_worker = User.objects.get(id=self.cleaned_data['to_worker_id'])
        except User.DoesNotExist:
            raise forms.ValidationError('Неверно указан сотрудник, кому хотите копировать расписание.')
        return trainee_worker.id

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['from_dt'] > self.cleaned_data['to_dt']:
            raise forms.ValidationError('Дата начала должна быть меньше даты конца.')


class GetCashierInfoForm(forms.Form):
    worker_id = forms.IntegerField()
    info = util_forms.MultipleChoiceField(['general_info', 'cashbox_type_info', 'constraints_info', 'work_hours'])


class GetWorkerDayForm(forms.Form):
    worker_id = forms.IntegerField()
    dt = util_forms.DateField()
    checkpoint = forms.IntegerField(required=False)


class SetWorkerDaysForm(forms.Form):
    worker_id = forms.IntegerField()
    dt_begin = util_forms.DateField()
    dt_end = util_forms.DateField()
    type = forms.CharField()
    dttm_work_start = util_forms.TimeField(required=False)
    dttm_work_end = util_forms.TimeField(required=False)
    checkpoint = forms.IntegerField(required=False)

    cashbox_type = forms.IntegerField(required=False)
    comment = forms.CharField(max_length=128, required=False)

    def clean_worker_id(self):
        try:
            worker = User.objects.get(id=self.cleaned_data['worker_id'])
        except User.DoesNotExist:
            raise forms.ValidationError('Invalid worker_id')
        return worker

    def clean_type(self):
        value = WorkerDayConverter.parse_type(self.cleaned_data['type'])
        if value is None:
            raise ValidationError('Invalid enum value')
        return value

    def clean(self):
        if self.errors:
            return

        if WorkerDay.is_type_with_tm_range(self.cleaned_data['type']):
            if self.cleaned_data.get('dttm_work_start') is None or self.cleaned_data.get('dttm_work_end') is None:
                raise ValidationError('dttm_work_start, dttm_work_end required')

        if self.cleaned_data['dt_begin'] > self.cleaned_data['dt_end']:
            raise forms.ValidationError('dt_begin have to be less or equal than dt_end')


class SetWorkerDayForm(forms.Form):
    worker_id = forms.IntegerField()
    dt = util_forms.DateField()
    type = forms.CharField()
    tm_work_start = util_forms.TimeField(required=False)
    tm_work_end = util_forms.TimeField(required=False)
    tm_break_start = util_forms.TimeField(required=False)

    cashbox_type = forms.IntegerField(required=False)
    comment = forms.CharField(max_length=128, required=False)
    details = forms.CharField(required=False)

    def clean_type(self):
        value = WorkerDayConverter.parse_type(self.cleaned_data['type'])
        if value is None:
            raise ValidationError('Invalid enum value')
        return value

    def clean(self):
        if self.errors:
            return

        if WorkerDay.is_type_with_tm_range(self.cleaned_data['type']):
            if self.cleaned_data.get('tm_work_start') is None:
                raise ValidationError('tm_work_start is required')
            if self.cleaned_data.get('tm_work_end') is None:
                raise ValidationError('tm_work_end is required')


class SetCashierInfoForm(forms.Form):
    worker_id = forms.IntegerField()
    work_type = forms.CharField(required=False)
    cashbox_info = forms.CharField(required=False)
    constraint = forms.CharField(required=False)
    comment = forms.CharField(required=False)
    sex = forms.CharField(required=False)
    is_fixed_hours = forms.BooleanField(required=False)
    is_fixed_days = forms.BooleanField(required=False)
    phone_number = forms.CharField(required=False),
    is_ready_for_overworkings = forms.BooleanField(required=False)
    tabel_code = forms.CharField(required=False)
    position_department = forms.IntegerField(required=False)
    position_title = forms.CharField(max_length=64, required=False)

    def clean_work_type(self):
        value = self.cleaned_data.get('work_type')
        if value is None or value == '':
            return None

        value = UserConverter.parse_work_type(value)
        if value is None:
            raise ValidationError('Invalid enum value')
        return value

    def clean_cashbox_info(self):
        try:
            value = self.cleaned_data.get('cashbox_info')
            if value is None or value == '':
                return None
            return json.loads(value)
        except:
            raise ValidationError('Invalid data')

    def clean_constraint(self):
        try:
            value = self.cleaned_data.get('constraint')
            if value is None or value == '':
                return None
            value = json.loads(value)
            value = {int(wd): [BaseConverter.parse_time(x) for x in tms] for wd, tms in value.items()}
        except:
            raise ValidationError('Invalid data')

        for wd in value:
            if wd < 0 or wd > 6:
                raise ValidationError('Invalid week day')

        return value


class CreateCashierForm(forms.Form):
    first_name = forms.CharField(max_length=30)
    middle_name = forms.CharField(max_length=64)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    password = forms.CharField(max_length=64)
    work_type = forms.CharField(max_length=3)
    dt_hired = util_forms.DateField()

    def clean_work_type(self):
        value = self.cleaned_data.get('work_type')
        if value is None or value == '':
            raise ValidationError('Invalid value')

        value = UserConverter.parse_work_type(value)
        if value is None:
            raise ValidationError('Invalid enum value')
        return value


class DeleteCashierForm(forms.Form):
    user_id = forms.IntegerField()
    dt_fired = util_forms.DateField()


class PasswordChangeForm(forms.Form):
    user_id = forms.IntegerField()
    old_password = forms.CharField(max_length=128, required=False)
    new_password = forms.CharField(max_length=128)


class ChangeCashierInfo(forms.Form):
    user_id = forms.IntegerField()
    first_name = forms.CharField(max_length=30, required=False)
    middle_name = forms.CharField(max_length=64, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    avatar = forms.ImageField(required=False)
    group = forms.CharField(max_length=1, required=False)
    birthday = forms.DateField(required=False)


class GetWorkerDayChangeLogsForm(forms.Form):
    shop_id = forms.IntegerField()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    pointer = forms.IntegerField()
    size = forms.IntegerField(required=False)
    worker_day_id = forms.IntegerField(required=False)


class DeleteWorkerDayChangeLogsForm(forms.Form):
    worker_day_id = forms.IntegerField()

