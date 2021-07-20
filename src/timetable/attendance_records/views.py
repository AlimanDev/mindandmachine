import io

import pandas as pd
from django.db.models import Case, When, Value, CharField
from django.http import HttpResponse
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext as _
from rest_framework.decorators import action

from src.base.permissions import Permission
from src.base.views_abstract import (
    BaseModelViewSet,
)
from src.timetable.models import AttendanceRecords
from .filters import AttendanceRecordsFilter
from .serializers import AttendanceRecordsSerializer


class AttendanceRecordsViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = AttendanceRecordsSerializer
    filterset_class = AttendanceRecordsFilter
    openapi_tags = ['AttendanceRecords', ]

    def get_queryset(self):
        return AttendanceRecords.objects

    @action(detail=False, methods=['get'], permission_classes=[Permission])
    def report(self, *args, **kwargs):
        att_records = self.filter_queryset(self.get_queryset()).annotate(
            type_name=Case(
                When(type=AttendanceRecords.TYPE_COMING, then=Value(_('Coming'), output_field=CharField())),
                When(type=AttendanceRecords.TYPE_LEAVING, then=Value(_('Leaving'), output_field=CharField())),
                default=Value(''), output_field=CharField()
            )
        ).values_list(
            'user__last_name',
            'user__first_name',
            'user__username',
            'employee__tabel_code',
            'shop__name',
            'shop__code',
            'type_name',
            'dttm',
        ).order_by('user__last_name', 'user__first_name', 'employee__tabel_code', 'dttm')
        df = pd.DataFrame(list(att_records), columns=(
            _('Last name'),
            _('First name'),
            _('Username'),
            _('Employee id'),
            _('Department name'),
            _('Department code'),
            _('Record type'),
            _('Date and time of the record'),
        ))
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, sheet_name=_('Records'), index=False)
        writer.save()
        output.seek(0)
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(self.action))
        return response
