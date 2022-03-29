import datetime
import io
import re
import time
from decimal import Decimal

import pandas as pd
import xlsxwriter
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q, F, Count, Sum, Prefetch
from django.db.models.expressions import OuterRef, Subquery, RawSQL
from django.db.models.functions import Coalesce
from django.http.response import HttpResponse
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

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
    TimesheetItem,
    WorkerDay,
    WorkType,
    WorkerDayType,
    WorkerDayCashboxDetails,
)
from src.timetable.worker_day.stat import WorkersStatsGetter
from src.timetable.worker_day.xlsx_utils.timetable import Timetable_xlsx

SKIP_SYMBOLS = ['NAN', '']
DIVIDERS = ['-', '.', ',', '\n', '\r', ' ']
MULTIPLE_WDAYS_DIVIDER = '/'
PARSE_CELL_STR_PATTERN = re.compile(
    r'(?P<excel_code>[а-яА-ЯA-Za-z]+)?(?P<time_str>~?\d{1,2}:\d{1,2}\s*[' + r'\\'.join(DIVIDERS) + r']\s*\d{1,2}:\d{1,2})?\s*(?P<work_type_name>\(\w+( +\w+)*\))?(?P<work_hours>\d*[.,]\d+|\d+)?')


class BaseUploadDownloadTimeTable:
    def __init__(self, user, form):
        self.user = user
        self.form = form
        self.shop_id = form['shop_id']
        self.shop = Shop.objects.get(pk=form['shop_id'])
        self.shop_work_type_id_by_name = {
            wt_tuple[0].lower(): wt_tuple[1] for wt_tuple in WorkType.objects.filter(
                shop_id=self.shop_id).values_list('work_type_name__name', 'id')
        }
        self.wd_types_dict = WorkerDayType.get_wd_types_dict()
        self.wd_type_mapping = {
            wd_type_code: wd_type.excel_load_code for wd_type_code, wd_type in self.wd_types_dict.items()}
        self.wd_type_mapping_reversed = dict((v, k) for k, v in self.wd_type_mapping.items())

    def _get_default_work_type(self, shop_id):
        default_work_type = WorkType.objects.filter(shop_id=shop_id, dttm_deleted__isnull=True).first()
        if not default_work_type:
            raise ValidationError({"message": _('There are no active work types in this shop.')})
        return default_work_type

    def _parse_cell_data(self, cell_data: str):
        cell_data = cell_data.strip()
        m = PARSE_CELL_STR_PATTERN.search(cell_data)
        if m:
            wd_type_id = WorkerDay.TYPE_WORKDAY
            excel_code = m.group('excel_code')
            if excel_code:
                wd_type_id = self.wd_type_mapping_reversed.get(excel_code)
                if wd_type_id is None:
                    return None, None, None, None, None, None

            time_str = m.group('time_str')
            if time_str:
                is_vacancy = False
                if time_str.startswith('~'):
                    is_vacancy = True
                    time_str = time_str.lstrip('~')
                for divider in DIVIDERS:
                    if divider in time_str:
                        times = time_str.split(divider)
                        work_type_name = m.group('work_type_name')
                        work_type_id = None
                        if work_type_name:  # TODO: тест
                            work_type_name = work_type_name.strip('()').lower()
                            work_type_id = self.shop_work_type_id_by_name.get(work_type_name)
                        return wd_type_id, work_type_id, is_vacancy, parse(times[0]).time(), parse(
                            times[1]).time(), None

            else:
                work_hours = m.group('work_hours')
                if work_hours:
                    return wd_type_id, None, None, None, None, work_hours.replace(',', '.')

        return None, None, None, None, None, None

    @staticmethod
    def _get_employment(employments_dict, employee_id, dt):
        employments = employments_dict.get(employee_id)
        for employment in employments:
            if employment.is_active(dt):
                return employment

    # TODO: рефакторинг + тест, что в рамках 1 загрузки берутся разные типы работ если несколько тр-в
    def _get_employments_dict(self, users, shop_id, dt_from, dt_to):
        employee_ids = list(map(lambda x: x[0].id, users))
        employments_dict = {}
        employments_list = list(Employment.objects.get_active_empl_by_priority(
            employee_id__in=employee_ids,
            priority_shop_id=shop_id,
            dt_from=dt_from,
            dt_to=dt_to,
        ).annotate(
            work_type_id=Subquery(
                EmploymentWorkType.objects.filter(
                    employment_id=OuterRef('id'),
                    work_type__shop_id=shop_id,
                ).order_by('-priority').values('work_type_id')[:1]
            )
        ))
        for employment in employments_list:
            employments_dict.setdefault(employment.employee_id, []).append(employment)
        return employments_dict

    def _get_employment_qs(self, network, shop_id, dt_from=None, dt_to=None):
        employment_extra_q = Q()
        if not network or network.settings_values_prop.get('timetable_exclude_invisible_employments', True):
            employment_extra_q &= Q(
                is_visible=True,
            )
        if not dt_from:
            dt_from = datetime.date.today()
        if not dt_to:
            dt_to = datetime.date.today()
        return Employment.objects.get_active(
            network_id=network.id if network else None,
            dt_from=dt_from,
            dt_to=dt_to,
            shop_id=shop_id,
            extra_q=employment_extra_q,
        ).select_related(
            'employee', 
            'employee__user', 
            'position',
        ).order_by('employee__user__last_name', 'employee__user__first_name', 'employee__user__middle_name', 'employee_id')

    def _get_worker_day_qs(self, employee_ids=[], dt_from=None, dt_to=None, is_approved=True, for_inspection=False):
        workdays = WorkerDay.objects.select_related('employee', 'employee__user', 'shop', 'type').filter(
            Q(dt__lte=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True) | Q(employment__isnull=True),
            (Q(dt__gte=F('employment__dt_hired')) | Q(employment__isnull=True)) & Q(dt__gte=dt_from),
            dt__lte=dt_to,
            is_approved=is_approved,
            is_fact=False,
        )

        if for_inspection:
            workdays = TimesheetItem.objects.select_related('employee', 'employee__user', 'shop', 'day_type').filter(
                dt__gte=dt_from,
                dt__lte=dt_to,
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
            )

        return workdays.filter(
            employee_id__in=employee_ids,
        ).order_by(
            'employee__user__last_name', 'employee__user__first_name', 'employee__user__middle_name', 'employee_id', 'dt', 'dttm_work_start',
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

        return employee_qs.distinct()

    def _get_worker_day_dict(self, shop_id, employee_qs, dt_from, dt_to, is_fact, is_approved):
        wdays_dict = {}
        wdays_qs = WorkerDay.objects.filter(
            Q(Q(type__is_dayoff=False) & Q(shop_id=shop_id)) |
                ~Q(type__is_dayoff=False),
                employee__in=employee_qs,
                dt__gte=dt_from,
                dt__lte=dt_to,
                is_fact=is_fact,
                is_approved=is_approved,
        ).select_related(
            'type',
        ).prefetch_related(
            Prefetch('worker_day_details',
                     queryset=WorkerDayCashboxDetails.objects.select_related('work_type__work_type_name'),
                     to_attr='worker_day_details_list'),
        )
        for wd in wdays_qs:
            wdays_dict.setdefault(f'{wd.employee_id}_{wd.dt}', []).append(wd)
        return wdays_dict

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
                    tabel_code = str(data[number_column]).split('.')[0].strip()
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
                        raise ValidationError(_('The employee with the full name {} does not exist in the current shop.').format(data[name_column]))
                
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
                            user = employee.user  # TODO: тест + рефакторинг
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

    def upload(self, timetable_file, is_fact=False):
        """
        Принимает от клиента экселевский файл и создает расписание (на месяц)
        """
        with transaction.atomic():
            shop_id = self.form['shop_id']

            try:
                df = pd.read_excel(timetable_file, dtype=str)
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

            users = self._get_users(users_df, number_column, name_column, position_column, shop_id, self.form['network_id'])

            res = self._upload(df, users, is_fact)

            employee_id__in = [u[0].id for u in users]
            WorkerDay.check_work_time_overlap(
                employee_id__in=employee_id__in, is_fact=False, is_approved=False, exc_cls=ValidationError)

        return res

    def download(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        workbook, name = self._download(workbook)
        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(name))
        return response
        
    def _download(self, workbook):
        raise NotImplementedError()

    def _upload(self, df, users, is_fact):
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

    def _group_worker_days(self, worker_days):
        wdays = {}
        for wd in worker_days:
            wdays.setdefault(wd.employee_id, {}).setdefault(wd.dt, []).append(wd)
        
        return wdays


class UploadDownloadTimetableCells(BaseUploadDownloadTimeTable):
    def _upload(self, df, users, is_fact):
        number_column = df.columns[0]
        name_column = df.columns[1]
        position_column = df.columns[2]
        shop_id = self.shop_id
        dates = []
        for dt in df.columns[3:]:
            if not isinstance(dt, datetime.datetime):
                break
            dates.append(dt.date())
        if not len(dates):
            return Response()

        default_work_type = self._get_default_work_type(shop_id)
        employments_dict = self._get_employments_dict(users, shop_id, dt_from=dates[0], dt_to=dates[-1])
        timetable_df = df[df.columns[:3 + len(dates)]]

        timetable_df[number_column] = timetable_df[number_column].astype(str)
        timetable_df[name_column] = timetable_df[name_column].astype(str)
        timetable_df[position_column] = timetable_df[position_column].astype(str)
        index_shift = 0

        new_wdays_data = []
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
                cell_str = str(data[i + 3]).upper().strip()
                cell_data_list = cell_str.split(MULTIPLE_WDAYS_DIVIDER)
                for cell_data in cell_data_list:
                    dttm_work_start = None
                    dttm_work_end = None
                    work_hours = None
                    wd_type_obj = None
                    work_type_id = None
                    is_vacancy = None
                    try:
                        if cell_data.replace(' ', '').replace('\n', '') in SKIP_SYMBOLS:
                            continue
                        if not (cell_data in self.wd_type_mapping_reversed):
                            wd_type_id, work_type_id, is_vacancy, tm_work_start, tm_work_end, work_hours = self._parse_cell_data(
                                cell_data)
                            wd_type_obj = self.wd_types_dict.get(wd_type_id)
                            if not (wd_type_obj.is_dayoff and wd_type_obj.is_work_hours and
                                    wd_type_obj.get_work_hours_method in [
                                        WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL, 
                                        WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL_OR_MONTH_AVERAGE_SAWH_HOURS
                            ]):
                                dttm_work_start = datetime.datetime.combine(
                                    dt, tm_work_start
                                )
                                dttm_work_end = datetime.datetime.combine(
                                    dt, tm_work_end
                                )
                                if dttm_work_end < dttm_work_start:
                                    dttm_work_end += datetime.timedelta(days=1)
                        elif not is_fact:
                            wd_type_id = self.wd_type_mapping_reversed[cell_data]
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

                    if not wd_type_obj:
                        wd_type_obj = self.wd_types_dict.get(wd_type_id)
                    employment = self._get_employment(employments_dict, employee.id, dt)
                    # TODO: перенести сюда проверку наличия активного тр-ва ???
                    new_wd_dict = dict(
                        employee_id=employee.id,
                        shop_id=shop_id if not wd_type_obj.is_dayoff else None,
                        dt=dt,
                        is_fact=is_fact,
                        is_approved=False,
                        employment=employment,
                        dttm_work_start=dttm_work_start,
                        dttm_work_end=dttm_work_end,
                        type_id=wd_type_id,
                        created_by=self.user,
                        last_edited_by=self.user,
                        closest_plan_approved=WorkerDay.get_closest_plan_approved_q(
                            employee_id=employee.id,
                            dt=dt,
                            dttm_work_start=dttm_work_start,
                            dttm_work_end=dttm_work_end,
                            delta_in_secs=self.user.network.set_closest_plan_approved_delta_for_manual_fact,
                        ).annotate(
                            order_by_val=RawSQL("""LEAST(
                                ABS(EXTRACT(EPOCH FROM (U0."dttm_work_start" - "timetable_workerday"."dttm_work_start"))),
                                ABS(EXTRACT(EPOCH FROM (U0."dttm_work_end" - "timetable_workerday"."dttm_work_end")))
                            )""", [])
                        ).order_by(
                            'order_by_val',
                        ).values('id').first() if (is_fact and not wd_type_obj.is_dayoff) else None,
                        source=WorkerDay.SOURCE_UPLOAD,
                        work_hours=datetime.timedelta(hours=float(work_hours)) if work_hours else None,
                    )
                    if wd_type_id == WorkerDay.TYPE_WORKDAY:
                        new_wd_dict['worker_day_details'] = [
                            dict(
                                work_type_id=work_type_id or employment.work_type_id or default_work_type.id,
                            )
                        ]
                    new_wd_dict['is_vacancy'] = WorkerDay.is_worker_day_vacancy(  # TODO: тест
                        employment.shop_id,
                        shop_id,
                        employment.work_type_id,
                        new_wd_dict.get('worker_day_details', []),
                        is_vacancy=is_vacancy,
                    )
                    new_wdays_data.append(new_wd_dict)

        objs, stats = WorkerDay.batch_update_or_create(
            data=new_wdays_data, user=self.user,
            check_perms_extra_kwargs=dict(
                check_active_empl=False,
                grouped_checks=True,
            ),
        )
        return Response(stats)

    def _download(self, workbook):
        ws = workbook.add_worksheet(_('Timetable for signature.'))
        timetable = Timetable_xlsx(
            workbook,
            self.shop,
            self.form['dt_from'],
            worksheet=ws,
            prod_days=None,
            on_print=self.form['on_print'],
            for_inspection=self.form.get('inspection_version', False),
        )

        employments = self._get_employment_qs(self.shop.network, self.shop_id, dt_from=timetable.prod_days[0].dt, dt_to=timetable.prod_days[-1].dt)
        employee_ids = employments.values_list('employee_id', flat=True)
        stat = WorkersStatsGetter(
            dt_from=timetable.prod_days[0].dt,
            dt_to=timetable.prod_days[-1].dt,
            shop_id=self.shop.id,
            employee_id__in=employee_ids,
        ).run()
        stat_type = 'approved' if self.form['is_approved'] else 'not_approved'
        norm_type = self.shop.network.settings_values_prop.get('download_timetable_norm_field', 'norm_work_hours')
        if self.form.get('inspection_version', False):
            main_stat = { 
                s['employee_id'] : s 
                for s in TimesheetItem.objects.filter(
                    employee_id__in=employee_ids,
                    shop_id=self.shop.id,
                    dt__gte=timetable.prod_days[0].dt,
                    dt__lte=timetable.prod_days[-1].dt,
                    timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                ).values(
                    'employee_id',
                ).annotate(
                    work_hours=Coalesce(Sum('day_hours', filter=Q(day_type__is_work_hours=True)), Decimal('0')) + Coalesce(Sum('night_hours', filter=Q(day_type__is_work_hours=True)), Decimal('0')),
                    work_days=Count('id', filter=Q(day_type__is_work_hours=True, day_type__is_dayoff=False)),
                    holidays=Count('id', filter=Q(day_type_id=WorkerDay.TYPE_HOLIDAY)),
                    vacations=Count('id', filter=Q(day_type_id=WorkerDay.TYPE_VACATION)),
                ).values('employee_id', 'work_hours', 'work_days', 'holidays', 'vacations')
            }
            for e in stat.keys():
                stat.setdefault(e, {}).setdefault('plan', {}).setdefault(stat_type, {}).setdefault('work_days', {})['total'] = main_stat.get(e, {}).get('work_days', 0)
                stat.setdefault(e, {}).setdefault('plan', {}).setdefault(stat_type, {}).setdefault('work_hours', {})['total'] = main_stat.get(e, {}).get('work_hours', 0)
                stat.setdefault(e, {}).setdefault('plan', {}).setdefault(stat_type, {}).setdefault('day_type', {})['H'] = main_stat.get(e, {}).get('holidays', 0)
                stat.setdefault(e, {}).setdefault('plan', {}).setdefault(stat_type, {}).setdefault('day_type', {})['V'] = main_stat.get(e, {}).get('vacations', 0)

        workdays = self._get_worker_day_qs(employee_ids=employee_ids, dt_from=timetable.prod_days[0].dt, dt_to=timetable.prod_days[-1].dt, is_approved=self.form['is_approved'], for_inspection=self.form.get('inspection_version', False))

        timetable.format_cells(len(employments))

        # construct weekday
        timetable.construct_dates('%w', 6, 3)

        # construct day 2
        timetable.construct_dates('%d.%m', 7, 3)
        timetable.add_main_info()

        # construct user info
        timetable.construnts_users_info(employments, 9, 0, ['code', 'fio', 'position'])

        grouped_days = self._group_worker_days(workdays)

        # fill page 1
        timetable.fill_table(grouped_days, employments, stat, 9, 3, stat_type=stat_type, norm_type=norm_type, mapping=self.wd_type_mapping)

        # fill page 2
        timetable.fill_table2(self.shop, timetable.prod_days[-1].dt, grouped_days)

        timetable.fill_description_table(self.wd_types_dict)

        if timetable.on_print:
            timetable.worksheet.set_landscape()
            timetable.worksheet.set_paper(9)
            timetable.worksheet.fit_to_pages(1, 0)
            timetable.worksheet.set_margins(left=0.25, right=0.25)
            timetable.print_worksheet.set_landscape()
            timetable.print_worksheet.set_paper(9)
            timetable.print_worksheet.fit_to_pages(1, 0)
            timetable.print_worksheet.set_margins(left=0.25, right=0.25)
            timetable.description_sheet.set_landscape()
            timetable.description_sheet.set_paper(9)
            timetable.description_sheet.fit_to_pages(1, 0)
            timetable.description_sheet.set_margins(left=0.25, right=0.25)

        return workbook, _('Timetable_for_shop_{}_from_{}.xlsx').format(self.shop.name, self.form['dt_from'])

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
                cell_values = []
                wdays_list = wdays_dict.get(f'{employee.id}_{dt}')
                if wdays_list:
                    for wd in wdays_list:
                        excel_code = self.wd_type_mapping.get(wd.type_id, '')
                        if wd.type.is_dayoff and wd.type.is_work_hours and wd.type.get_work_hours_method in [
                                WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL, 
                                WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL_OR_MONTH_AVERAGE_SAWH_HOURS
                        ]:
                            _cell_value = excel_code + str(round(wd.work_hours.total_seconds() / 3600, 2))
                            cell_values.append(_cell_value)
                        elif not wd.type.is_dayoff:
                            tm_start = wd.dttm_work_start.strftime('%H:%M') if wd.dttm_work_start else '??:??'
                            tm_end = wd.dttm_work_end.strftime('%H:%M') if wd.dttm_work_end else '??:??'
                            _cell_value = f'{tm_start}-{tm_end}'
                            if not wd.type_id == WorkerDay.TYPE_WORKDAY:
                                _cell_value = excel_code + _cell_value
                            if self.shop.network.settings_values_prop.get('allow_to_manually_set_is_vacancy'):
                                if wd.type.has_details and wd.worker_day_details_list:
                                    _cell_value += '({})'.format(
                                        wd.worker_day_details_list[0].work_type.work_type_name.name)
                                if wd.is_vacancy:
                                    _cell_value = '~' + _cell_value
                            cell_values.append(_cell_value)
                        else:
                            cell_values.append(excel_code)

                row_data[dt] = f'{MULTIPLE_WDAYS_DIVIDER}'.join(cell_values) if cell_values else ''

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

    def _download(self, workbook):
        def _get_active_empl(wd, empls):
            if wd.employment:
                return wd.employment
            return list(filter(
                lambda e: (e.dt_hired is None or e.dt_hired <= wd.dt) and (
                            e.dt_fired is None or wd.dt <= e.dt_fired),
                empls.get(wd.employee_id, []),
            ))[0]

        dt_from = self.form['dt_from']
        dt_to = dt_from + relativedelta(day=31)

        empls = {}
        employments = self._get_employment_qs(self.shop.network, self.shop.id, dt_from=dt_from, dt_to=dt_to)
        employee_ids = employments.values_list('employee_id', flat=True)
        for e in employments:
            empls.setdefault(e.employee_id, []).append(e)
        
        workdays = self._get_worker_day_qs(
            employee_ids=employee_ids, dt_from=dt_from, dt_to=dt_to, is_approved=self.form['is_approved']
        ).select_related('employment', 'employment__position')

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
                    'start': wd.dttm_work_start.time().strftime('%H:%M') if wd.dttm_work_start else self.wd_type_mapping[wd.type_id],
                    'end': wd.dttm_work_end.time().strftime('%H:%M') if wd.dttm_work_end else self.wd_type_mapping[wd.type_id],
                }
            )
        
        data = {
            'shop': self.shop,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'sheet_name': _('Timetable for signature.'),
            'rows': rows,
        }

        return self._generate_workbook(workbook, data)

    def _upload(self, df, users, is_fact):
        def _get_str_data(row):
            return str(row).strip().upper().replace(' ', '').replace('\n', '')

        number_column = df.columns[0]
        name_column = df.columns[1]
        position_column = df.columns[2]
        dt_column = df.columns[3]
        start_column = df.columns[4]
        end_column = df.columns[5]
        shop_id = self.shop_id
        df[number_column] = df[number_column].astype(str)
        df[name_column] = df[name_column].astype(str)
        df[position_column] = df[position_column].astype(str)

        employees = {}

        for data in users:
            employees[data[0].tabel_code] = data

        stats = {}

        default_work_type = self._get_default_work_type(shop_id)
        employments_dict = self._get_employments_dict(
            users, shop_id, dt_from=df[dt_column].min(), dt_to=df[dt_column].max())
        with transaction.atomic():
            new_wdays_data = []
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

                wd_type_obj = self.wd_types_dict.get(type_of_work)
                employment = self._get_employment(employments_dict, employee.id, dt)
                new_wd_data = dict(
                    employee_id=employee.id,
                    shop_id=shop_id if not wd_type_obj.is_dayoff else None,
                    dt=dt,
                    is_fact=is_fact,
                    is_approved=False,
                    employment=employment,
                    dttm_work_start=dttm_work_start,
                    dttm_work_end=dttm_work_end,
                    type_id=type_of_work,
                    created_by=self.user,
                    last_edited_by=self.user,
                    closest_plan_approved=WorkerDay.get_closest_plan_approved_q(
                        employee_id=employee.id,
                        dt=dt,
                        dttm_work_start=dttm_work_start,
                        dttm_work_end=dttm_work_end,
                        delta_in_secs=self.user.network.set_closest_plan_approved_delta_for_manual_fact,
                    ).first() if (is_fact and not wd_type_obj.is_dayoff) else None,
                    source=WorkerDay.SOURCE_UPLOAD,
                )
                if type_of_work == WorkerDay.TYPE_WORKDAY:
                    new_wd_data['worker_day_details'] = [
                        dict(
                            work_type_id=employment.work_type_id or default_work_type.id,
                        )
                    ]
                new_wdays_data.append(new_wd_data)

            objs, stats = WorkerDay.batch_update_or_create(
                data=new_wdays_data, user=self.user,
                check_perms_extra_kwargs=dict(
                    check_active_empl=False,
                    grouped_checks=True,
                ),
            )

        return Response(stats)

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
                wdays_list = wdays_dict.get(f'{employee.id}_{dt}', [])
                row_data = {
                    'dt': str(dt),
                    'tabel_code': employee.tabel_code or '',
                    'fio': employee.user.fio,
                    'position': employee.position or '',
                    'start': '',
                    'end': '',
                }

                if wdays_list:
                    for wd in wdays_list:  # TODO: нехватает типа дня? Как отличать командировку от рабочего дня, например?
                        row_data = row_data.copy()
                        if wd.type.is_dayoff and wd.type.is_work_hours and wd.type.get_work_hours_method in [
                                WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL, 
                                WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL_OR_MONTH_AVERAGE_SAWH_HOURS
                        ]:
                            # TODO: доработать экспорт и импорт
                            row_data['work_hours'] = str(round(wd.work_hours.total_seconds() / 3600))
                        else:
                            row_data['start'] = wd.dttm_work_start.strftime(
                                '%H:%M') if not wd.type.is_dayoff else self.wd_type_mapping.get(wd.type_id, '')
                            row_data['end'] = wd.dttm_work_end.strftime(
                                '%H:%M') if not wd.type.is_dayoff else self.wd_type_mapping.get(wd.type_id, '')
                        rows.append(row_data)
                else:
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
