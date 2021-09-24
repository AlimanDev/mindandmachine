from src.forecast.period_clients.utils import upload_demand_util_v3
from src.base.forms import DefaultOverrideAdminWidgetsForm
from django import forms
from django.db.models import Q
from datetime import date, timedelta
from src.base.models import Shop 
from src.forecast.models import LoadTemplate, OperationTypeName 
from src.forecast.load_template.tasks import calculate_shops_load
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple

class LoadTemplateAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'forecast_params',
    ]

def get_templates():
    return LoadTemplate.objects.all()

def get_shops():
    return Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=date.today()),
    )

def get_operations():
    return OperationTypeName.objects.all()

class RecalcLoadForm(forms.Form):
    dt_from = forms.DateField(initial=date.today(), label='Дата с', required=True, widget=AdminDateWidget)
    dt_to = forms.DateField(initial=date.today() + timedelta(days=30), label='Дата по', required=True, widget=AdminDateWidget)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['load_templates'] = forms.ModelMultipleChoiceField(queryset=get_templates(), label='Шаблоны нагрузки', required=False, widget=FilteredSelectMultiple('Шаблоны нагрузки', is_stacked=False))
        self.fields['shops'] = forms.ModelMultipleChoiceField(queryset=get_shops(), label='Магазины', required=False, widget=FilteredSelectMultiple('Отделы', is_stacked=False))

    def recalc_load(self, dt_from, dt_to, load_templates=[], shops=[]):
        if len(shops):
            for shop in shops:
                calculate_shops_load.delay(shop.load_template_id, dt_from, dt_to, shop_id=shop.id)
        else:
            for template in load_templates:
                calculate_shops_load.delay(template.id, dt_from, dt_to)

class UploadDemandForm(forms.Form):
    file = forms.FileField()
    type = forms.ChoiceField(choices=[('F', 'Факт'), ('L', 'Прогноз')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['operation_type_name'] = forms.ModelChoiceField(queryset=get_operations(), label='Тип операций')

    def upload_demand(self, operation_type_name, file, type):
        return upload_demand_util_v3(operation_type_name, file, type=type)
