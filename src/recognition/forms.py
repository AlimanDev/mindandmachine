from django import forms
from datetime import date
from src.base.models import Network
from django.contrib.admin.widgets import AdminDateWidget
from src.util.urv.urv_violators import urv_violators_report_xlsx_v2
from dateutil.relativedelta import relativedelta
from django.http.response import HttpResponse


class DownloadViolatorsReportForm(forms.Form):
    dt_from = forms.DateField(initial=date.today(), label='Дата с', required=True, widget=AdminDateWidget)
    dt_to = forms.DateField(initial=date.today() + relativedelta(day=31), label='Дата по', required=True, widget=AdminDateWidget)
    exclude_created_by = forms.BooleanField(initial=False, help_text='Исключить ручные изменения', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['network'] = forms.ModelChoiceField(queryset=Network.objects.all(), label='Сеть')

    def get_file(self, network, dt_from, dt_to, exclude_created_by):
        data = urv_violators_report_xlsx_v2(network_id=network.id, dt_from=dt_from, dt_to=dt_to, in_memory=True, exclude_created_by=exclude_created_by)
        response = HttpResponse(data['file'], content_type=data['type'])
        response['Content-Disposition'] = f'attachment; filename="{data["name"]}"'
        return response
