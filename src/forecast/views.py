from django.views.generic.edit import FormView
from src.forecast.forms import RecalcLoadForm, UploadDemandForm
from src.timetable.mixins import SuperuserRequiredMixin


class RecalcLoadAdminView(SuperuserRequiredMixin, FormView):
    form_class = RecalcLoadForm
    template_name = 'recalc_load.html'
    success_url = '/admin/forecast/loadtemplate/'

    def form_valid(self, form):
        load_templates = form.cleaned_data['load_templates']
        shops = form.cleaned_data['shops']
        dt_from = form.cleaned_data['dt_from']
        dt_to = form.cleaned_data['dt_to']
        if not load_templates and not shops:
            return super().form_valid(form)
        
        form.recalc_load(dt_from.strftime('%Y-%m-%dT%H:%M:%S'), dt_to.strftime('%Y-%m-%dT%H:%M:%S'), load_templates=load_templates, shops=shops)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['title'] = 'Пересчет нагрузки'
        context['has_permission'] = True

        return context

class UploadDemandAdminView(SuperuserRequiredMixin, FormView):
    form_class = UploadDemandForm
    template_name = 'upload_demand.html'
    success_url = '/admin/forecast/periodclients/'

    def form_valid(self, form):
        operation_type_name = form.cleaned_data['operation_type_name']
        file = form.cleaned_data['file']
        type = form.cleaned_data['type']
        if not (operation_type_name and file and type):
            return super().form_invalid(form)
        
        form.upload_demand(operation_type_name, file, type)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['title'] = 'Загрузка нагрузки'
        context['has_permission'] = True

        return context
