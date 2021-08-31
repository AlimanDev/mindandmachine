import datetime
import io
import time
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models.expressions import OuterRef, Subquery
from django.http.response import HttpResponse
from django.utils.encoding import escape_uri_path

import pandas as pd
from django.conf import settings
from django.db.models import Q, F
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from dateutil.parser import parse
import xlsxwriter

from src.base.models import (
    Network,
    User,
    Shop,
    Employment,
    WorkerPosition,
    Group,
    Employee,
)
from src.timetable.models import (
    EmploymentWorkType,
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
)
from src.timetable.worker_day.stat import WorkersStatsGetter
from src.timetable.worker_day.xlsx_utils.timetable import Timetable_xlsx
from src.util.models_converter import Converter

SKIP_SYMBOLS = ['NAN', '']
DIVIDERS = ['-', '.', ',', '\n', ' ']

class BaseUploadDownloadTimeTable:

    def __init__(self):
        self.wd_type_mapping = {
            WorkerDay.TYPE_BUSINESS_TRIP: _('BT'),
            WorkerDay.TYPE_HOLIDAY: _('H'),
            WorkerDay.TYPE_ABSENSE: _('ABS'),
            WorkerDay.TYPE_REAL_ABSENCE: 'ПР',  # пока что нет на фронте
            WorkerDay.TYPE_QUALIFICATION: _('ST'),
            WorkerDay.TYPE_SICK: _('S'),
            WorkerDay.TYPE_VACATION: _('V'),
            WorkerDay.TYPE_EXTRA_VACATION: 'ОД',  # пока что нет на фронте
            WorkerDay.TYPE_STUDY_VACATION: 'У',  # пока что нет на фронте
            WorkerDay.TYPE_SELF_VACATION: _('VO'),
            WorkerDay.TYPE_SELF_VACATION_TRUE: 'ОЗ',  # пока что нет на фронте
            WorkerDay.TYPE_GOVERNMENT: 'Г',  # пока что нет на фронте
            WorkerDay.TYPE_MATERNITY: _('MAT'),
            WorkerDay.TYPE_MATERNITY_CARE: 'Р',  # пока что нет на фронте
            WorkerDay.TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE: 'ОВ',  # пока что нет на фронте
            WorkerDay.TYPE_ETC: '',
            WorkerDay.TYPE_EMPTY: '',
        }
        self.wd_type_mapping_reversed = dict((v, k) for k, v in self.wd_type_mapping.items())

    def _get_times(self, time_str: str):
        time_str = time_str.strip()
        for divider in DIVIDERS:
            if divider in time_str:
                times = time_str.split(divider)
                return parse(times[0]).time(), parse(times[1]).time()

    def _get_employment_work_types(self, users, shop_id):
        default_work_type = WorkType.objects.filter(shop_id=shop_id, dttm_deleted__isnull=True).first()
        if not default_work_type:
            raise ValidationError({"message": _('There are no active work types in this shop.')})
        employments = list(map(lambda x: x[1].id, users))
        priority_subq = EmploymentWorkType.objects.filter(
            employment_id=OuterRef('employment_id'),
            is_active=True,
        ).order_by('priority')
        work_types = EmploymentWorkType.objects.filter(
            employment_id__in=employments,
            is_active=True,
            id=Subquery(priority_subq.values_list('id', flat=True)[:1]),
        )
        employment_work_type = dict.fromkeys(employments, default_work_type.id)
        for wt in work_types:
            employment_work_type[wt.employment_id] = wt.work_type_id
        
        return employment_work_type

    def _get_employment_qs(self, network_id, shop_id, dt_from=None, dt_to=None):
        if not dt_from:
            dt_from = datetime.date.today()
        if not dt_to:
            dt_to = datetime.date.today()
        return Employment.objects.get_active(
            network_id=network_id,
            dt_from=dt_from,
            dt_to=dt_to,
            shop_id=shop_id,
        ).select_related(
            'employee', 
            'employee__user', 
            'position',
        ).order_by('employee__user__last_name', 'employee__user__first_name', 'employee__user__middle_name', 'employee_id')

    def _get_worker_day_qs(self, employee_ids=[], dt_from=None, dt_to=None, is_approved=True):
        workdays = WorkerDay.objects.select_related('employee', 'employee__user', 'shop').filter(
            Q(dt__lte=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True) | Q(employment__isnull=True),
            (Q(dt__gte=F('employment__dt_hired')) | Q(employment__isnull=True)) & Q(dt__gte=dt_from),
            employee_id__in=employee_ids,
            dt__lte=dt_to,
            is_approved=is_approved,
            is_fact=False,
        ).order_by(
            'employee__user__last_name', 'employee__user__first_name', 'employee__user__middle_name', 'employee_id', 'dt')

        return workdays.get_last_ordered(
            is_fact=False,
            order_by=[
                '-is_approved' if is_approved else 'is_approved',
                '-is_vacancy',
                '-id',
            ]
        )

    def _get_employee_qs(self, network_id, shop_id, dt_from, dt_to, employee_id__in):
        employee_qs = Employee.objects.filter(
            employments__id__in=Employment.objects.get_active(
                network_id=network_id,
                shop_id=shop_id,
                dt_from=dt_from,
                dt_to=dt_to,
                is_visible=True,
            )
        ).annotate(
            position=Subquery(Employment.objects.get_active(
                network_id=network_id,
                shop_id=shop_id,
                dt_from=dt_from,
                dt_to=dt_to,
                is_visible=True,
                employee_id=OuterRef('id'),
            ).order_by('-norm_work_hours').values('position__name')[:1])
        ).select_related(
            'user',
        ).order_by('user__last_name', 'user__first_name')

        if employee_id__in:
            employee_qs = employee_qs.filter(id__in=employee_id__in)

        return employee_qs

    def _get_worker_day_dict(self, shop_id, employee_qs, dt_from, dt_to, is_fact, is_approved):
        return {
            f'{wd.employee_id}_{wd.dt}': wd for wd in WorkerDay.objects.filter(
                Q(Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE) & Q(shop_id=shop_id)) |
                ~Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                employee__in=employee_qs,
                dt__gte=dt_from,
                dt__lte=dt_to,
                is_fact=is_fact,
                is_approved=is_approved,
            )
        }

    def _get_users(self, df, number_column, name_column, position_column, shop_id, network_id):
        network = Network.objects.get(id=network_id)
        if not network.add_users_from_excel:
            users = []
            for index, data in df.iterrows():
                if data[number_column].startswith('*') or data[name_column].startswith('*') or data[position_column].startswith('*'):
                    continue
                number_cond = data[number_column] != 'nan'
                name_cond = data[name_column] != 'nan'
                employment = None
                tabel_code = ''
                if number_cond:
                    tabel_code = str(data[number_column]).split('.')[0]
                    employment = Employment.objects.filter(
                        employee__tabel_code=tabel_code, 
                        shop_id=shop_id,
                    ).select_related('employee').order_by('dt_hired').first()
                elif name_cond:
                    names = data[name_column].split()
                    employment = Employment.objects.filter(
                        shop_id=shop_id,
                        employee__user__first_name=names[1] if len(names) > 1 else '',
                        employee__user__last_name=names[0],
                        employee__user__middle_name=names[2] if len(names) > 2 else None
                    ).select_related('employee').order_by('dt_hired').first()
                else:
                    continue
                
                if not employment:
                    if number_cond:
                        raise ValidationError(_('The employee with number {} does not exist in the current shop.').format(tabel_code))
                    else:
                        raise ValidationError(_('The employee with the full name {} does not exist in the current shop.').format(data[name_cond]))
                
                users.append([
                    employment.employee,
                    employment,
                ])
            return users
        else:
            return self._upload_employments(df, number_column, name_column, position_column, shop_id, network_id)


    def _upload_employments(self, df, number_column, name_column, position_column, shop_id, network_id):
        groups = {
            f.name.lower(): f
            for f in Group.objects.all()
        }
        positions = {
            p.name.lower(): p
            for p in WorkerPosition.objects.all()
        }
        error_users = []
        users = []
        with transaction.atomic():
            for index, data in df.iterrows():
                if data[number_column].startswith('*') or data[name_column].startswith('*') or data[position_column].startswith('*'):
                    continue
                number_cond = data[number_column] != 'nan'
                name_cond = data[name_column] != 'nan'
                position_cond = data[position_column] != 'nan'
                if number_cond and (not position_cond or not name_cond):
                    fields = ""
                    if not number_cond:
                        fields += _("tabel code ")
                    if not name_cond:
                        fields += _("full name ")
                    if not position_cond:
                        fields += _("position ")
                    result = _("The employee's {} are not recognized or specified on the line {}.").format(fields, index)
                    error_users.append(result)
                    continue
                elif not position_cond:
                    continue
                elif not name_cond:
                    continue
                position = positions.get(data[position_column].lower().strip())
                if not position:
                    raise ValidationError({"message": _('There is no such position {position}.').format(position=data[position_column])})
                names = data[name_column].split()
                tabel_code = str(data[number_column]).split('.')[0].strip()
                created = False
                user_data = {
                    'first_name': names[1] if len(names) > 1 else '',
                    'last_name': names[0],
                    'middle_name': names[2] if len(names) > 2 else None,
                    'network_id': network_id,
                }
                user = None
                if settings.UPLOAD_TT_MATCH_EMPLOYMENT:
                    employment = Employment.objects.filter(employee__tabel_code=tabel_code, shop_id=shop_id)
                    if number_cond and employment.exists():
                        employee = employment.first().employee  # TODO: покрыть тестами
                        user = employee.user
                        if user.last_name != names[0]:
                            error_users.append(
                                _("The employee on the line {} with the table number {} has the last name {} in the system, but in the file {}.").format(
                                    index, tabel_code, user.last_name, names[0]
                                )
                            )
                            continue
                        user.first_name = names[1] if len(names) > 1 else ''
                        user.last_name = names[0]
                        user.middle_name = names[2] if len(names) > 2 else None
                        user.save()
                    else:
                        employment = Employment.objects.filter(
                            shop_id=shop_id,
                            employee__user__first_name=names[1] if len(names) > 1 else '',
                            employee__user__last_name=names[0],
                            employee__user__middle_name=names[2] if len(names) > 2 else None
                        )
                        if employment.exists() and settings.UPLOAD_TT_CREATE_EMPLOYEE:
                            employee = employment.first().employee
                            if number_cond and employee.tabel_code != tabel_code:
                                user = employee.user
                                employee = Employee.objects.create(user=user, tabel_code=tabel_code)
                                created = True
                        else:
                            user_data['username'] = str(time.time() * 1000000)[:-2],
                            user = User.objects.create(**user_data)
                            employee = Employee.objects.create(user=user, tabel_code=tabel_code)
                            created = True
                else:
                    employees_qs = Employee.objects.filter(tabel_code=tabel_code)
                    if number_cond and employees_qs.exists():
                        User.objects.filter(employees__in=employees_qs).update(**user_data)
                        employee = employees_qs.first()
                    else:
                        employee = Employee.objects.filter(
                            **{'user__' + k: v for k,v in user_data.items()}
                        )
                        if employee.exists() and settings.UPLOAD_TT_CREATE_EMPLOYEE:
                            employee = employee.first()
                            if number_cond and employee.tabel_code != tabel_code:
                                user = employee.user
                                employee = Employee.objects.create(user=user, tabel_code=tabel_code)
                                created = True
                        else:
                            user_data['username'] = str(time.time() * 1000000)[:-2]
                            user = User.objects.create(**user_data)
                            employee = Employee.objects.create(user=user, tabel_code=tabel_code)
                            created = True
                func_group = groups.get(data[position_column].lower().strip(), groups['сотрудник'])
                if created:
                    employee.user.username = f'u{user.id}'
                    employee.user.save()
                    employment = Employment.objects.create(
                        shop_id=shop_id,
                        employee=employee,
                        function_group=func_group,
                        position=position,
                    )
                    if settings.UPLOAD_TT_MATCH_EMPLOYMENT and number_cond:
                        employee.tabel_code = tabel_code
                        employee.save(update_fields=('tabel_code',))
                else:
                    employment = Employment.objects.get_active(
                        network_id=user.network_id,
                        employee=employee,
                    ).first()
                    if not employment:
                        employment = Employment.objects.create(
                            shop_id=shop_id,
                            employee=employee,
                            position=position,
                            function_group=func_group,
                        )
                    else:
                        employment.position = position
                        employment.save()
                users.append([
                    employee,
                    employment,
                ])
            if len(error_users):
                raise ValidationError({"message": '\n'.join(error_users)})

        return users

    def upload(self, form, timetable_file, is_fact=False):
        """
        Принимает от клиента экселевский файл и создает расписание (на месяц)
        """
        with transaction.atomic():
            shop_id = form['shop_id']

            try:
                df = pd.read_excel(timetable_file)
            except KeyError:
                raise ValidationError({"message": _('Failed to open active sheet.')})
            ######################### сюда писать логику чтения из экселя ######################################################

            users_df = df[df.columns[:3]].drop_duplicates()
            number_column = df.columns[0]
            name_column = df.columns[1]
            position_column = df.columns[2]
            users_df[number_column] = users_df[number_column].astype(str)
            users_df[name_column] = users_df[name_column].astype(str)
            users_df[position_column] = users_df[position_column].astype(str)

            users = self._get_users(users_df, number_column, name_column, position_column, shop_id, form['network_id'])

            res = self._upload(df, users, form, is_fact)

            employee_id__in = [u[0].id for u in users]
            WorkerDay.check_work_time_overlap(employee_id__in=employee_id__in, exc_cls=ValidationError)

        return res

    def download(self, form):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        workbook, name = self._download(workbook, form)
        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(name))
        return response
        
    def _download(self, workbook, form):
        raise NotImplementedError()

    def _upload(self, df, users, form, is_fact):
        raise NotImplementedError()

    def generate_upload_example(self, *args):
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        workbook, name = self._generate_upload_example(writer, *args)
        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(name))
        return response

    def _generate_upload_example(self, workbook, shop_id, dt_from, dt_to, is_fact, is_approved, employee_id__in):
        raise NotImplementedError()

class UploadDownloadTimetableCells(BaseUploadDownloadTimeTable):

    def _upload(self, df, users, form, is_fact):
        number_column = df.columns[0]
        name_column = df.columns[1]
        position_column = df.columns[2]
        shop_id = form['shop_id']
        dates = []
        for dt in df.columns[3:]:
            if not isinstance(dt, datetime.datetime):
                break
            dates.append(dt.date())
        if not len(dates):
            return Response()

        employment_work_types = self._get_employment_work_types(users, shop_id)
        timetable_df = df[df.columns[:3 + len(dates)]]

        timetable_df[number_column] = timetable_df[number_column].astype(str)
        timetable_df[name_column] = timetable_df[name_column].astype(str)
        timetable_df[position_column] = timetable_df[position_column].astype(str)
        index_shift = 0

        for index, data in timetable_df.iterrows():
            if data[number_column].startswith('*') or data[name_column].startswith('*') \
                or data[position_column].startswith('*'):
                index_shift += 1
                continue
            number_cond = data[number_column] != 'nan'
            name_cond = data[name_column] != 'nan'
            position_cond = data[position_column] != 'nan'
            if not number_cond and (not name_cond or not position_cond):
                index_shift += 1
                continue
            employee, employment = users[index - index_shift]
            work_type = employment_work_types[employment.id]
            for i, dt in enumerate(dates):
                dttm_work_start = None
                dttm_work_end = None
                try:
                    cell_data = str(data[i + 3]).upper().strip()
                    if cell_data.replace(' ', '').replace('\n', '') in SKIP_SYMBOLS:
                        continue
                    if not (cell_data in self.wd_type_mapping_reversed):
                        tm_work_start, tm_work_end = self._get_times(data[i + 3])
                        type_of_work = WorkerDay.TYPE_WORKDAY
                        dttm_work_start = datetime.datetime.combine(
                            dt, tm_work_start
                        )
                        dttm_work_end = datetime.datetime.combine(
                            dt, tm_work_end
                        )
                        if dttm_work_end < dttm_work_start:
                            dttm_work_end += datetime.timedelta(days=1)
                    elif not is_fact:
                        type_of_work = self.wd_type_mapping_reversed[cell_data]
                    else:
                        continue
                except Exception as e:
                    raise ValidationError(
                        {
                            "message": _('The employee {user.first_name} {user.last_name} in the cell for {dt} has the wrong value: {value}.').format(
                                user=employee.user, 
                                dt=dt, 
                                value=str(data[i + 3]
                            ))
                        }
                    )

                WorkerDay.objects.filter(dt=dt, employee=employee, is_fact=is_fact, is_approved=False).delete()
            
                new_wd = WorkerDay.objects.create(
                    employee=employee,
                    shop_id=shop_id,
                    dt=dt,
                    is_fact=is_fact,
                    is_approved=False,
                    employment=employment,
                    dttm_work_start=dttm_work_start,
                    dttm_work_end=dttm_work_end,
                    type=type_of_work,
                )
                if type_of_work == WorkerDay.TYPE_WORKDAY:
                    WorkerDayCashboxDetails.objects.create(
                        worker_day=new_wd,
                        work_type_id=work_type,
                    )

        return Response()

    def _download(self, workbook, form):
        ws = workbook.add_worksheet(_('Timetable for signature.'))
        shop = Shop.objects.get(pk=form['shop_id'])
        timetable = Timetable_xlsx(
            workbook,
            shop,
            form['dt_from'],
            worksheet=ws,
            prod_days=None
        )

        employments = self._get_employment_qs(shop.network_id, shop.id, dt_from=timetable.prod_days[0].dt, dt_to=timetable.prod_days[-1].dt)
        employee_ids = employments.values_list('employee_id', flat=True)
        stat = WorkersStatsGetter(
            dt_from=timetable.prod_days[0].dt,
            dt_to=timetable.prod_days[-1].dt,
            shop_id=shop.id,
            employee_id__in=employee_ids,
        ).run()
        stat_type = 'approved' if form['is_approved'] else 'not_approved'

        workdays = self._get_worker_day_qs(employee_ids=employee_ids, dt_from=timetable.prod_days[0].dt, dt_to=timetable.prod_days[-1].dt, is_approved=form['is_approved'])

        if form.get('inspection_version', False):
            timetable.change_for_inspection(timetable.prod_month.get('norm_work_hours', 0), workdays)

        timetable.format_cells(len(employments))

        # construct weekday
        timetable.construct_dates('%w', 8, 4)

        # construct day 2
        timetable.construct_dates('%d.%m', 9, 4)
        timetable.add_main_info()

        # construct user info
        timetable.construnts_users_info(employments, 11, 0, ['code', 'fio', 'position'])

        # fill page 1
        timetable.fill_table(workdays, employments, stat, 11, 4, stat_type=stat_type, mapping=self.wd_type_mapping)

        # fill page 2
        timetable.fill_table2(shop, timetable.prod_days[-1].dt, workdays)

        return workbook, _('Timetable_for_shop_{}_from_{}.xlsx').format(shop.name, form['dt_from'])

    def _generate_upload_example(self, writer, shop_id, dt_from, dt_to, is_fact, is_approved, employee_id__in):
        shop = Shop.objects.get(id=shop_id)
        employee_qs = self._get_employee_qs(shop.network_id, shop_id, dt_from, dt_to, employee_id__in)

        wdays_dict = self._get_worker_day_dict(shop_id, employee_qs, dt_from, dt_to, is_fact, is_approved)

        rows = []
        dates = list(
            pd.date_range(dt_from, dt_to).date)
        for employee in employee_qs:
            row_data = {}
            row_data[_('Employee id')] = employee.tabel_code
            row_data[_('Full name')] = employee.user.fio  # TODO: разделить на 3 поля
            row_data[_('Position')] = employee.position
            for dt in dates:
                _cell_value = ''

                wd = wdays_dict.get(f'{employee.id}_{dt}')
                if wd:
                    if wd.type in WorkerDay.TYPES_WITH_TM_RANGE:
                        tm_start = wd.dttm_work_start.strftime('%H:%M')
                        tm_end = wd.dttm_work_end.strftime('%H:%M')
                        _cell_value = f'{tm_start}-{tm_end}'
                    else:
                        _cell_value = self.wd_type_mapping.get(wd.type, '')

                row_data[dt] = _cell_value

            rows.append(row_data)

        if not rows:
            df = pd.DataFrame(columns=[_('Employee id'), _('Full name'), _('Position')] + dates)
        else:
            df = pd.DataFrame(rows)
        sheet_name = _('Timetable')
        df.to_excel(
            excel_writer=writer, sheet_name=sheet_name, index=False,
            columns=[_('Employee id'), _('Full name'), _('Position')] + dates,
        )
        worksheet = writer.sheets[sheet_name]
        # set the column width as per your requirement
        for idx, col in enumerate(df):  # loop through all columns
            series = df[col]
            max_len = max((
                series.astype(str).map(len).max(),  # len of largest item
                len(str(series.name))  # len of column name/header
            )) + 2  # adding a little extra space
            worksheet.set_column(idx, idx, max_len)
        
        return writer.book, f'Timetable_{shop.name}_{dt_from}_{dt_to}.xlsx'

class UploadDownloadTimetableRows(BaseUploadDownloadTimeTable):

    def _generate_workbook(self, workbook, data):
        ws = workbook.add_worksheet(data['sheet_name'])

        header_format = workbook.add_format({
            'border': 1,
            'bold': True,
            'text_wrap': True,
            'valign': 'vcenter',
            'align': 'center',
        })
        def_dict_format = {
            'border': 1,
            'valign': 'vcenter',
            'align': 'center',
            'text_wrap': True,
        }
        gray_format_dict = def_dict_format.copy()
        gray_format_dict['bg_color'] = '#dedede'
        def_format = workbook.add_format(def_dict_format)
        gray_format = workbook.add_format(gray_format_dict)
        
        TABEL_COL = 0
        FIO_COL = 1
        POSITION_COL = 2
        DT_COL = 3
        START_COL = 4
        END_COL = 5
        ws.write_string(0, TABEL_COL, _("Employee id"), header_format)
        ws.set_column(TABEL_COL, TABEL_COL, 12)
        ws.write_string(0, FIO_COL, _("Full name"), header_format)
        ws.set_column(FIO_COL, FIO_COL, 30)
        ws.write_string(0, POSITION_COL, _("Position"), header_format)
        ws.set_column(POSITION_COL, POSITION_COL, 12)
        ws.write_string(0, DT_COL, _("Date"), header_format)
        ws.set_column(DT_COL, DT_COL, 10)
        ws.write_string(0, START_COL, _("Shift start"), header_format)
        ws.set_column(START_COL, START_COL, 10)
        ws.write_string(0, END_COL, _("Shift end"), header_format)
        ws.set_column(END_COL, END_COL, 10)

        row = 1
        for r in data['rows']:
            style = gray_format if row % 2 == 1 else def_format 
            ws.write_string(row, TABEL_COL, r['tabel_code'], style)
            ws.write_string(row, FIO_COL,r['fio'], style)
            ws.write_string(row, POSITION_COL, r['position'], style)
            ws.write_string(row, DT_COL, r['dt'], style)
            ws.write_string(row, START_COL, r['start'], style)
            ws.write_string(row, END_COL, r['end'], style)
            row += 1

        return workbook, _('Timetable_for_shop_{}_from_{}.xlsx').format(data['shop'].name, data['dt_from'])

    def _download(self, workbook, form):
        def _get_active_empl(wd, empls):
            if wd.employment:
                return wd.employment
            return list(filter(
                lambda e: (e.dt_hired is None or e.dt_hired <= wd.dt) and (
                            e.dt_fired is None or wd.dt <= e.dt_fired),
                empls.get(wd.employee_id, []),
            ))[0]


        shop = Shop.objects.get(pk=form['shop_id'])
        dt_from = form['dt_from']
        dt_to = dt_from + relativedelta(day=31)

        empls = {}
        employments = self._get_employment_qs(shop.network_id, shop.id, dt_from=dt_from, dt_to=dt_to)
        employee_ids = employments.values_list('employee_id', flat=True)
        for e in employments:
            empls.setdefault(e.employee_id, []).append(e)
        
        workdays = self._get_worker_day_qs(employee_ids=employee_ids, dt_from=dt_from, dt_to=dt_to, is_approved=form['is_approved']).select_related('employment', 'employment__position')

        rows = []

        for wd in workdays:
            active_empl = _get_active_empl(wd, empls)
            if not active_empl:
                continue
            rows.append(
                {
                    'tabel_code': wd.employee.tabel_code or '',
                    'fio': wd.employee.user.get_fio(),
                    'position': active_empl.position.name if active_empl.position else 'Не указано',
                    'dt': str(wd.dt),
                    'start': wd.dttm_work_start.time().strftime('%H:%M') if wd.dttm_work_start else self.wd_type_mapping[wd.type],
                    'end': wd.dttm_work_end.time().strftime('%H:%M') if wd.dttm_work_end else self.wd_type_mapping[wd.type],
                }
            )
        
        data = {
            'shop': shop,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'sheet_name': _('Timetable for signature.'),
            'rows': rows,
        }

        return self._generate_workbook(workbook, data)

    def _upload(self, df, users, form, is_fact):
        def _get_str_data(row):
            return str(row).strip().upper().replace(' ', '').replace('\n', '')

        number_column = df.columns[0]
        name_column = df.columns[1]
        position_column = df.columns[2]
        dt_column = df.columns[3]
        start_column = df.columns[4]
        end_column = df.columns[5]
        shop_id = form['shop_id']
        df[number_column] = df[number_column].astype(str)
        df[name_column] = df[name_column].astype(str)
        df[position_column] = df[position_column].astype(str)

        employees = {}

        for data in users:
            employees[data[0].tabel_code] = data
        
        employment_work_types = self._get_employment_work_types(users, shop_id)
        
        with transaction.atomic():
            for i, data in df.iterrows():
                if data[number_column].startswith('*') or data[name_column].startswith('*') \
                    or data[position_column].startswith('*'):
                    continue
                number_cond = data[number_column] != 'nan'
                name_cond = data[name_column] != 'nan'
                position_cond = data[position_column] != 'nan'
                if not number_cond and (not name_cond or not position_cond):
                    continue
                employee, employment = employees[str(data[number_column]).split('.')[0].strip()]
                work_type = employment_work_types[employment.id]
                dttm_work_start = None
                dttm_work_end = None
                if _get_str_data(data[start_column]) in SKIP_SYMBOLS:
                    continue
                try:
                    dt = pd.to_datetime(data[dt_column]).date()
                except:
                    raise ValidationError({"message": _('Can not parse date value {} on row {}.').format(data[dt_column], i + 2)})
                try:
                    type = _get_str_data(data[start_column])
                    if not (type in self.wd_type_mapping_reversed):
                        start, end = _get_str_data(data[start_column]), _get_str_data(data[end_column])
                        type_of_work = WorkerDay.TYPE_WORKDAY
                        dttm_work_start = datetime.datetime.combine(
                            dt, parse(start).time()
                        )
                        dttm_work_end = datetime.datetime.combine(
                            dt, parse(end).time()
                        )
                        if dttm_work_end < dttm_work_start:
                            dttm_work_end += datetime.timedelta(days=1)
                    elif not is_fact:
                        type_of_work = self.wd_type_mapping_reversed[type]
                    else:
                        continue
                except Exception as e:
                    raise ValidationError(
                        {
                            "message": _('The employee {user.first_name} {user.last_name} in the row {i} has the wrong value: {value}.').format(
                                user=employee.user, 
                                i=i + 2,
                                value=data[start_column]
                            )
                        }
                    )

                WorkerDay.objects.filter(dt=dt, employee=employee, is_fact=is_fact, is_approved=False).delete()
            
                new_wd = WorkerDay.objects.create(
                    employee=employee,
                    shop_id=shop_id,
                    dt=dt,
                    is_fact=is_fact,
                    is_approved=False,
                    employment=employment,
                    dttm_work_start=dttm_work_start,
                    dttm_work_end=dttm_work_end,
                    type=type_of_work,
                )
                if type_of_work == WorkerDay.TYPE_WORKDAY:
                    WorkerDayCashboxDetails.objects.create(
                        worker_day=new_wd,
                        work_type_id=work_type,
                    )

        return Response()      

    def _generate_upload_example(self, wrtier, shop_id, dt_from, dt_to, is_fact, is_approved, employee_id__in):
        workbook = wrtier.book
        shop = Shop.objects.get(id=shop_id)
        employee_qs = self._get_employee_qs(shop.network_id, shop_id, dt_from, dt_to, employee_id__in)

        wdays_dict = self._get_worker_day_dict(shop_id, employee_qs, dt_from, dt_to, is_fact, is_approved)

        rows = []
        dates = list(
            pd.date_range(dt_from, dt_to).date)
        for employee in employee_qs:
            for dt in dates:
                row_data = {
                    'dt': str(dt),
                    'tabel_code': employee.tabel_code or '',
                    'fio': employee.user.fio,
                    'position': employee.position or '',
                    'start': '',
                    'end': '',
                }
                wd = wdays_dict.get(f'{employee.id}_{dt}')
                
                if wd:
                    row_data['start'] = wd.dttm_work_start.strftime('%H:%M') if wd.type in WorkerDay.TYPES_WITH_TM_RANGE else self.wd_type_mapping.get(wd.type, '')
                    row_data['end'] = wd.dttm_work_end.strftime('%H:%M') if wd.type in WorkerDay.TYPES_WITH_TM_RANGE else self.wd_type_mapping.get(wd.type, '')
                rows.append(row_data)

        data = {
            'shop': shop,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'sheet_name': _('Timetable'),
            'rows': rows,
        }

        return self._generate_workbook(workbook, data)


timetable_formats = {
    'cell_format': UploadDownloadTimetableCells,
    'row_format': UploadDownloadTimetableRows,
}

def get_timetable_generator_cls(timetable_format='cell_format'):
    tabel_generator_cls = timetable_formats.get(timetable_format)
    return tabel_generator_cls
