from django import forms
from datetime import date
from django.db.models import Q
from src.base.models import Network, User, Shop, Employment
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from src.reports.utils.urv_violators import urv_violators_report_xlsx_v2
from dateutil.relativedelta import relativedelta
from django.http.response import HttpResponse


def get_users():
    user_ids = Employment.objects.get_active().values_list('user_id', flat=True)
    return User.objects.filter(id__in=user_ids)

def get_shops():
    return Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=date.today()),
    )


class DownloadViolatorsReportForm(forms.Form):
    dt_from = forms.DateField(initial=date.today(), label='Дата с', required=True, widget=AdminDateWidget)
    dt_to = forms.DateField(initial=date.today() + relativedelta(day=31), label='Дата по', required=True, widget=AdminDateWidget)
    exclude_created_by = forms.BooleanField(initial=False, help_text='Исключить ручные изменения', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['network'] = forms.ModelChoiceField(queryset=Network.objects.all(), label='Сеть')
        self.fields['users'] = forms.ModelMultipleChoiceField(queryset=get_users(), label='Пользователи', required=False, widget=FilteredSelectMultiple('Пользователи', is_stacked=False))
        self.fields['shops'] = forms.ModelMultipleChoiceField(queryset=get_shops(), label='Магазины', required=False, widget=FilteredSelectMultiple('Отделы', is_stacked=False))

    def get_file(self, network, dt_from, dt_to, exclude_created_by, user_ids=None, shop_ids=None):
        data = urv_violators_report_xlsx_v2(network_id=network.id, dt_from=dt_from, dt_to=dt_to, in_memory=True, exclude_created_by=exclude_created_by, user_ids=user_ids, shop_ids=shop_ids)
        response = HttpResponse(data['file'], content_type=data['type'])
        response['Content-Disposition'] = f'attachment; filename="{data["name"]}"'
        return response
