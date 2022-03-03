from django import forms
from django.db.models import Q
from datetime import date, timedelta
from src.base.models import User, Shop, Employment
from src.timetable.worker_day.tasks import recalc_wdays
from src.timetable.timesheet.tasks import calc_timesheets
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from src.base.forms import CustomSelectWidget, DefaultOverrideAdminWidgetsForm


class ExchangeSettingsForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'constraints',
    ]


def get_users():
    user_ids = Employment.objects.get_active().values_list('employee__user_id', flat=True)
    return User.objects.filter(id__in=user_ids)

def get_shops():
    return Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=date.today()),
    )

class RecalsWhForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dt_from'] = forms.DateField(initial=date.today(), label='Дата с', required=True, widget=AdminDateWidget)
        self.fields['dt_to'] = forms.DateField(initial=date.today() + timedelta(days=90), label='Дата по', required=True, widget=AdminDateWidget)
        self.fields['users'] = forms.ModelMultipleChoiceField(queryset=get_users(), label='Пользователи', required=False, widget=FilteredSelectMultiple('Пользователи', is_stacked=False))
        self.fields['shops'] = forms.ModelMultipleChoiceField(queryset=get_shops(), label='Магазины', required=False, widget=FilteredSelectMultiple('Отделы', is_stacked=False))

    def recalc_wh(self, **kwargs):
        recalc_wdays.delay(**kwargs)
    
class RecalsTimesheetForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dt_from'] = forms.DateField(initial=date.today().replace(day=1), label='Дата с', required=True, widget=AdminDateWidget, help_text='Внимание: День будет заменен на 1 число.')
        self.fields['users'] = forms.ModelMultipleChoiceField(queryset=get_users(), label='Пользователи', required=False, widget=FilteredSelectMultiple('Пользователи', is_stacked=False))
        self.fields['shops'] = forms.ModelMultipleChoiceField(queryset=get_shops(), label='Магазины', required=False, widget=FilteredSelectMultiple('Отделы', is_stacked=False))

    def recalc_timesheet(self, **kwargs):
        calc_timesheets.delay(**kwargs)

class GroupWorkerDayPermissionForm(forms.ModelForm):
    class Meta:
        widgets = {
            'worker_day_permission': CustomSelectWidget,
        }
