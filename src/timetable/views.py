from django.views.generic.edit import FormView
from src.base.permissions import FilteredListPermission
from src.timetable.filters import EmploymentWorkTypeFilter
from src.timetable.models import (
    EmploymentWorkType,
)
from src.timetable.serializers import (
    EmploymentWorkTypeSerializer,
)
from src.base.views_abstract import BaseModelViewSet
from src.timetable.forms import RecalsWhForm
from src.timetable.mixins import SuperuserRequiredMixin


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
