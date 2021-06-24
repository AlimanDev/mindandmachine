import datetime
import time
from dateutil.relativedelta import relativedelta
from django.db import transaction

import pandas as pd
from django.db.models import Q, F
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from src.base.models import (
    User,
    Shop,
    Employment,
    WorkerPosition,
    Group,
    Employee,
)
from src.conf.djconfig import UPLOAD_TT_MATCH_EMPLOYMENT
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
)
from src.timetable.worker_day.stat import WorkersStatsGetter
from src.timetable.worker_day.xlsx_utils.timetable import Timetable_xlsx
from src.util.download import xlsx_method
from src.util.models_converter import Converter

SKIP_SYMBOLS = ['NAN', '']

class BaseUploadDownloadTimeTable:

    def get_employment_qs(self, network_id, shop_id, dt_from=None, dt_to=None):
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

    def get_worker_day_qs(self, employee_ids=[], dt_from=None, dt_to=None, is_approved=True):
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
                    # Нет такой должности {position}
                    raise ValidationError(_('There is no such position {position}.').format(position=data[position_column]))
                names = data[name_column].split()
                tabel_code = str(data[number_column]).split('.')[0]
                created = False
                user_data = {
                    'first_name': names[1] if len(names) > 1 else '',
                    'last_name': names[0],
                    'middle_name': names[2] if len(names) > 2 else None,
                    'network_id': network_id,
                }
                user = None
                if UPLOAD_TT_MATCH_EMPLOYMENT:
                    employment = Employment.objects.filter(employee__tabel_code=tabel_code, shop=shop)
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
                        if employment.exists():
                            employee = employment.first().employee
                            if number_cond:
                                employee.tabel_code = tabel_code
                                employee.save(update_fields=('tabel_code',))
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
                        if employee.exists():
                            if number_cond:
                                employee.update(tabel_code=tabel_code,)
                            employee = employee.first()
                        else:
                            user_data['username'] = str(time.time() * 1000000)[:-2]
                            if number_cond:
                                user_data['tabel_code'] = tabel_code
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
                    if UPLOAD_TT_MATCH_EMPLOYMENT and number_cond:
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

    def upload(self, file, is_fact=False):
        raise NotImplementedError()

    @xlsx_method
    def download(self, request, workbook, form):
        raise NotImplementedError()

class UploadDownloadTimetableV1(BaseUploadDownloadTimeTable):
    def upload(self, timetable_file, form, is_fact=False):
        """
        Принимает от клиента экселевский файл и создает расписание (на месяц)
        """
        shop_id = form['shop_id']

        try:
            df = pd.read_excel(timetable_file)
        except KeyError:
            raise ValidationError(_('Failed to open active sheet.'))
        ######################### сюда писать логику чтения из экселя ######################################################

        users_df = df[df.columns[:3]]
        number_column = df.columns[0]
        name_column = df.columns[1]
        position_column = df.columns[2]
        users_df[number_column] = users_df[number_column].astype(str)
        users_df[name_column] = users_df[name_column].astype(str)
        users_df[position_column] = users_df[position_column].astype(str)

        users = self._upload_employments(users_df, number_column, name_column, position_column, shop_id, form['network_id'])
        
        dates = []
        for dt in df.columns[3:]:
            if not isinstance(dt, datetime.datetime):
                break
            dates.append(dt.date())
        if not len(dates):
            return Response()

        work_types = {
            w.work_type_name.name.lower(): w
            for w in WorkType.objects.select_related('work_type_name').filter(shop_id=shop_id, dttm_deleted__isnull=True)
        }
        if (len(work_types) == 0):
            raise ValidationError(_('There are no active work types in this shop.'))

        first_type = next(iter(work_types.values()))
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
            for i, dt in enumerate(dates):
                dttm_work_start = None
                dttm_work_end = None
                try:
                    cell_data = str(data[i + 3]).upper().strip()
                    if cell_data.replace(' ', '').replace('\n', '') in SKIP_SYMBOLS:
                        continue
                    if not (cell_data in WorkerDay.WD_TYPE_MAPPING_REVERSED):
                        splited_cell = data[i + 3].replace('\n', '').strip().split()
                        work_type = work_types.get(data[position_column].upper(), first_type) if len(splited_cell) == 1 else work_types.get(splited_cell[1].upper(), first_type)
                        times = splited_cell[0].split('-')
                        type_of_work = WorkerDay.TYPE_WORKDAY
                        dttm_work_start = datetime.datetime.combine(
                            dt, Converter.parse_time(times[0] + ':00')
                        )
                        dttm_work_end = datetime.datetime.combine(
                            dt, Converter.parse_time(times[1] + ':00')
                        )
                        if dttm_work_end < dttm_work_start:
                            dttm_work_end += datetime.timedelta(days=1)
                    elif not is_fact:
                        type_of_work = WorkerDay.WD_TYPE_MAPPING_REVERSED[cell_data]
                    else:
                        continue
                except Exception as e:
                    raise ValidationError(_('The employee {user.first_name} {user.last_name} in the cell for {dt} has the wrong value: {value}.').format(user=employee.user, dt=dt, value=str(data[i + 3])))

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
                        work_type=work_type,
                    )

        return Response()

    @xlsx_method
    def download(self, request, workbook, form):
        ws = workbook.add_worksheet(_('Timetable for signature.'))

        shop = Shop.objects.get(pk=form['shop_id'])
        timetable = Timetable_xlsx(
            workbook,
            shop,
            form['dt_from'],
            worksheet=ws,
            prod_days=None
        )

        employments = self.get_employment_qs(shop.network_id, shop.id, dt_from=timetable.prod_days[0].dt, dt_to=timetable.prod_days[-1].dt)
        employee_ids = employments.values_list('employee_id', flat=True)
        stat = WorkersStatsGetter(
            dt_from=timetable.prod_days[0].dt,
            dt_to=timetable.prod_days[-1].dt,
            shop_id=shop.id,
            employee_id__in=employee_ids,
        ).run()
        stat_type = 'approved' if form['is_approved'] else 'not_approved'

        workdays = self.get_worker_day_qs(employee_ids=employee_ids, dt_from=timetable.prod_days[0].dt, dt_to=timetable.prod_days[-1].dt, is_approved=form['is_approved'])

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
        timetable.fill_table(workdays, employments, stat, 11, 4, stat_type=stat_type)

        # fill page 2
        timetable.fill_table2(shop, timetable.prod_days[-1].dt, workdays)

        return workbook, _('Timetable_for_shop_{}_from_{}.xlsx').format(shop.name, form['dt_from'])


class UploadDownloadTimetableV2(BaseUploadDownloadTimeTable):
    def download(self, request, workbook, form):
        def _get_active_empl(wd, empls):
            if wd.employment:
                return wd.employment
            return list(filter(
                lambda e: (e.dt_hired is None or e.dt_hired <= wd.dt) and (
                            e.dt_fired is None or wd.dt <= e.dt_fired),
                empls.get(wd.employee_id, []),
            ))[0]

        ws = workbook.add_worksheet(_('Timetable for signature.'))

        shop = Shop.objects.get(pk=form['shop_id'])
        dt_from = form['dt_from']
        dt_to = dt_from + relativedelta(month=1)
        
        empls = {}
        employments = self.get_employment_qs(shop.network_id, shop.id, dt_from=dt_from, dt_to=dt_to)
        employee_ids = employments.values_list('employee_id', flat=True)
        for e in employments:
            empls.setdefault(e.employee_id, []).append(e)
        
        workdays = self.get_worker_day_qs(employee_ids=employee_ids, dt_from=dt_from, dt_to=dt_to, is_approved=form['is_approved']).select_related('employment', 'employment__position')

        TABEL_COL = 0
        FIO_COL = 1
        POSITION_COL = 2
        DT_COL = 3
        START_COL = 4
        END_COL = 5
        ws.write_string(0, TABEL_COL, _("Employee id"))
        ws.write_string(0, FIO_COL, _("Full name"))
        ws.write_string(0, POSITION_COL, _("Position"))
        ws.write_string(0, DT_COL, _("Date"))
        ws.write_string(0, START_COL, _("Shift start"))
        ws.write_string(0, END_COL, _("Shift end"))

        row = 1
        for wd in workdays:
            active_empl = _get_active_empl(wd, empls)
            if not active_empl or not active_empl.position:
                continue
            ws.write_string(row, TABEL_COL, wd.employee.tabel_code)
            ws.write_string(row, FIO_COL, wd.employee.user.get_fio())
            ws.write_string(row, POSITION_COL, active_empl.position.name)
            ws.write_string(row, DT_COL, str(wd.dt))
            ws.write_string(row, START_COL, wd.dttm_work_start.time().strftime('%H:%M'))
            ws.write_string(row, END_COL, wd.dttm_work_end.time().strftime('%H:%M'))

        return workbook, _('Timetable_for_shop_{}_from_{}.xlsx').format(shop.name, form['dt_from'])


    @xlsx_method
    def upload(self, file, is_fact):
        pass
