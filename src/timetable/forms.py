from django import forms
from django.db.models import Q
from datetime import date, timedelta
from src.base.models import User, Shop, Employment
from src.timetable.worker_day.tasks import recalc_wdays
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple



def get_users():
    user_ids = Employment.objects.get_active().values_list('user_id', flat=True)
    return User.objects.filter(id__in=user_ids)

def get_shops():
    return Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=date.today()),
    )

class RecalsWhForm(forms.Form):
    dt_from = forms.DateField(initial=date.today(), label='Дата с', required=True, widget=AdminDateWidget)
    dt_to = forms.DateField(initial=date.today() + timedelta(days=90), label='Дата по', required=True, widget=AdminDateWidget)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['users'] = forms.ModelMultipleChoiceField(queryset=get_users(), label='Пользователи', required=False, widget=FilteredSelectMultiple('Пользователи', is_stacked=False))
        self.fields['shops'] = forms.ModelMultipleChoiceField(queryset=get_shops(), label='Магазины', required=False, widget=FilteredSelectMultiple('Отделы', is_stacked=False))

    def recalc_wh(self, **kwargs):
        recalc_wdays.delay(**kwargs)
