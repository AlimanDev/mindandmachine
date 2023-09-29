

class AttendanceRecordsService:
    def report(self, qs):
        att_records = qs.annotate(
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
        writer = pd.ExcelWriter(output, engine='xlsxwriter')  # TODO: move to openpyxl
        df.to_excel(writer, sheet_name=_('Records'), index=False)
        writer.save()
        output.seek(0)
