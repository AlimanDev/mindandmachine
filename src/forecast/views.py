from django.views.generic.edit import FormView
from src.forecast.forms import RecalcLoadForm
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
