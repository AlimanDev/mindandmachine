from dateutil.relativedelta import relativedelta
from django.views.generic.edit import FormView
from src.apps.base.models import Employee
from src.apps.base.permissions import FilteredListPermission
from src.apps.timetable.filters import EmploymentWorkTypeFilter
from src.apps.timetable.models import (
    EmploymentWorkType,
)
from src.interfaces.api.serializers.timetable import (
    EmploymentWorkTypeSerializer,
)
from src.apps.base.views_abstract import BaseModelViewSet
from src.apps.timetable.forms import RecalsTimesheetForm, RecalsWhForm
from src.apps.timetable.mixins import SuperuserRequiredMixin


class EmploymentWorkTypeViewSet(BaseModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentWorkTypeSerializer
    filterset_class = EmploymentWorkTypeFilter
    queryset = EmploymentWorkType.objects.all()
    openapi_tags = ['EmploymentWorkType',]


class RecalcWhAdminView(SuperuserRequiredMixin, FormView):
    form_class = RecalsWhForm
    template_name = 'recalc_wh.html'
    success_url = '/admin/timetable/workerday/'

    def form_valid(self, form):
        users = form.cleaned_data['users']
        shops = form.cleaned_data['shops']
        dt_from = form.cleaned_data['dt_from']
        dt_to = form.cleaned_data['dt_to']
        if not users and not shops:
            return super().form_valid(form)

        kwargs = {
            'dt__gte': dt_from.strftime('%Y-%m-%d'),
            'dt__lte': dt_to.strftime('%Y-%m-%d'),
        }

        if users:
            kwargs['employee__user_id__in'] = list(users.values_list('id', flat=True))
        if shops:
            kwargs['shop_id__in'] = list(shops.values_list('id', flat=True))
        
        form.recalc_wh(**kwargs)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['title'] = 'Пересчет рабочих часов'
        context['has_permission'] = True

        return context

class RecalcTimesheetAdminView(SuperuserRequiredMixin, FormView):
    form_class = RecalsTimesheetForm
    template_name = 'recalc_timesheet.html'
    success_url = '/admin/timetable/workerday/'

    def form_valid(self, form):
        users = form.cleaned_data['users']
        shops = form.cleaned_data['shops']
        dt_from = form.cleaned_data['dt_from']

        kwargs = {
            'dt_from': dt_from.replace(day=1).strftime('%Y-%m-%d'),
            'dt_to': (dt_from + relativedelta(day=31)).strftime('%Y-%m-%d'),
        }

        employee_qs = Employee.objects.all()

        if users:
            employee_qs = employee_qs.filter(user__in=users)
        if shops:
            employee_qs = employee_qs.filter(employments__shop__in=shops).distinct('id')
        
        kwargs['employee_id__in'] = list(employee_qs.values_list('id', flat=True))
        
        form.recalc_timesheet(**kwargs)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['title'] = 'Пересчет табеля'
        context['has_permission'] = True

        return context

