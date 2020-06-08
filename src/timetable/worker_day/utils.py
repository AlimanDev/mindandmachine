import pandas as pd
import time
import datetime
from src.base.models import (
    User,
    Shop,
    Employment,
    WorkerPosition,
    Group,
)
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
)
from src.util.models_converter import Converter
from django.db.models import Q, F
from src.timetable.worker_day.xlsx_utils.timetable import Timetable_xlsx
from src.timetable.worker_day.xlsx_utils.tabel import Tabel_xlsx
from src.util.download import xlsx_method
from src.main.urv.utils import wd_stat_count
import json
from src.base.exceptions import MessageError
from rest_framework.response import Response


WORK_TYPES = {
    'в': WorkerDay.TYPE_HOLIDAY,
    'от': WorkerDay.TYPE_VACATION,
    'nan': WorkerDay.TYPE_HOLIDAY,
    'b': WorkerDay.TYPE_HOLIDAY,
}

def upload_timetable_util(form, timetable_file):
    """
    Принимает от клиента экселевский файл и создает расписание (на месяц)
    """
    shop_id = form['shop_id']
    shop = Shop.objects.get(id=shop_id)

    try:
        df = pd.read_excel(timetable_file)
    except KeyError:
        raise MessageError(code='xlsx_no_active_list', lang=form.get('lang', 'ru'))
    ######################### сюда писать логику чтения из экселя ######################################################

    users = []

    users_df = df[df.columns[:3]]
    groups = {
        f.name.lower(): f
        for f in Group.objects.all()
    }
    positions = {
        p.name.lower(): p
        for p in WorkerPosition.objects.all()
    }
    users_df['Номер'] = users_df['Номер'].astype(str)

    for index, data in users_df.iterrows():
        if data['Номер'].startswith('*') or data['Номер'] == 'nan':
            continue
        position = positions.get(data['ДОЛЖНОСТЬ'].lower())
        if not position:
            raise MessageError('xlsx_no_worker_position', lang=form.get('lang', 'ru'), params={'position':data["ДОЛЖНОСТЬ"]})
        names = data['ФИО'].split()
        user, created = User.objects.get_or_create(
            tabel_code=str(data['Номер']).split('.')[0],
            defaults={
                'first_name': names[1],
                'last_name': names[0],
                'middle_name': names[2] if len(names) > 2 else None,
                'username': str(time.time() * 1000000)[:-2]
            }
        )
        func_group = groups.get(data['ДОЛЖНОСТЬ'].lower(), groups['сотрудник'])
        if created:
            user.username = f'u{user.id}'
            user.save()
            employment = Employment.objects.create(
                shop_id=shop_id,
                user=user,
                function_group=func_group,
                position=position,
            )
        else:
            employment, _ = Employment.objects.update_or_create(
                shop_id=shop_id,
                user=user,
                defaults={
                    'function_group': func_group,
                    'position': position,
                }
            )
        users.append([
            user,
            employment,
        ])
    
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
    first_type = next(iter(work_types.values()))
    timetable_df = df[df.columns[:3 + len(dates)]]

    timetable_df['Номер'] = timetable_df['Номер'].astype(str)


    for index, data in timetable_df.iterrows():
        if data['Номер'].startswith('*') or data['Номер'] == 'nan':
            continue
        user, employment = users[index]
        for i, dt in enumerate(dates):
            dttm_work_start = None
            dttm_work_end = None
            try:
                if not (str(data[i + 3]).lower() in WORK_TYPES):
                    splited_cell = data[i + 3].replace('\n', '').split()
                    work_type = first_type if len(splited_cell) == 1 else work_types.get(splited_cell[1].lower(), first_type)
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
                else:
                    type_of_work = WORK_TYPES[str(data[i + 3]).lower()]
            except:
                raise MessageError(code='xlsx_undefined_cell', lang=form.get('lang', 'ru'), params={'user': user, 'i': i + 1})
            wd_query_set = list(WorkerDay.objects.filter(dt=dt, worker=user).order_by('-id'))
            WorkerDayCashboxDetails.objects.filter(
                worker_day__in=wd_query_set,
            ).delete()
            for wd in wd_query_set:  # потому что могут быть родители у wd
                wd.delete()
            new_wd, created = WorkerDay.objects.filter(Q(shop_id=shop_id)|Q(shop__isnull=True)).update_or_create(
                worker=user,
                shop_id=shop_id,
                dt=dt,
                is_fact=False,
                is_approved=False,
                defaults={
                    'employment':employment,
                    'dttm_work_start':dttm_work_start,
                    'dttm_work_end':dttm_work_end,
                    'type':type_of_work,
                }
            )
            if type_of_work == WorkerDay.TYPE_WORKDAY:
                if not created:
                    WorkerDayCashboxDetails.filter(worker_day=new_wd).delete()
                WorkerDayCashboxDetails.objects.create(
                    worker_day=new_wd,
                    work_type=work_type,
                )

    return Response()

@xlsx_method
def download_timetable_util(request, workbook, form):
    ws = workbook.add_worksheet('Расписание на подпись')

    shop = Shop.objects.get(pk=form['shop_id'])
    timetable = Timetable_xlsx(
        workbook,
        shop,
        form['dt_from'],
        worksheet=ws,
        prod_days=None
    )

    employments = Employment.objects.get_active(
        dt_from=timetable.prod_days[0].dt,
        dt_to=timetable.prod_days[-1].dt,
        shop=shop,
    ).order_by('position_id', 'user__last_name', 'user__first_name', 'user__middle_name', 'tabel_code', 'id')

    breaktimes = json.loads(shop.settings.break_triplets)
    breaktimes = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), breaktimes))

    workdays = WorkerDay.objects.select_related('worker', 'shop').filter(
        Q(dt__lt=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True),
        Q(dt__gte=F('employment__dt_hired')) & Q(dt__gte=timetable.prod_days[0].dt),
        employment__in=employments,
        dt__lte=timetable.prod_days[-1].dt,
        is_approved=form['is_approved'],
        is_fact=False,
    ).order_by(
        'employment__position_id', 'worker__last_name', 'worker__first_name', 'worker__middle_name', 'employment__tabel_code', 'employment__id', 'dt')

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
    timetable.fill_table(workdays, employments, breaktimes, 11, 4)

    # fill page 2
    timetable.fill_table2(shop, timetable.prod_days[-1].dt, workdays)

    return workbook, 'Cashiers_timetable'


@xlsx_method
def download_tabel_util(request, workbook, form):
    """
    Скачать табель на дату
    Args:
        method: GET
        url: api/download/get_tabel
        shop_id(int): required = False
        weekday(QOS_DATE): на какую дату табель хотим
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)
    Returns:
        Табель
    """
    ws = workbook.add_worksheet(Tabel_xlsx.MONTH_NAMES[form['dt_from'].month])

    shop = Shop.objects.get(pk=form['shop_id'])

    tabel = Tabel_xlsx(
        workbook,
        shop,
        form['dt_from'],
        worksheet=ws,
        prod_days=None
    )

    from_dt = tabel.prod_days[0].dt
    to_dt = tabel.prod_days[-1].dt

    employments = Employment.objects.get_active(
        dt_from=from_dt,
        dt_to=to_dt,
        shop=shop,
    ).select_related('position').order_by('position_id', 'user__last_name', 'user__first_name', 'tabel_code', 'id')

    workdays = WorkerDay.objects.select_related('worker', 'shop').filter(
        Q(dt__lt=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True),
        Q(dt__gte=F('employment__dt_hired')) & Q(dt__gte=from_dt),
        employment__in=employments,
        dt__lte=to_dt,
        is_approved=form['is_approved'],
        is_fact=False,
    ).order_by('employment__position_id', 'worker__last_name', 'worker__first_name', 'employment__tabel_code', 'employment__id', 'dt')

    wd_stat = wd_stat_count(workdays, shop)
    working_hours = {}
    for wd in wd_stat:
        if wd['worker_id'] not in working_hours:
            working_hours[wd['worker_id']] = {}
        working_hours[wd['worker_id']][wd['dt']] = wd['hours_fact']

    breaktimes = json.loads(shop.settings.break_triplets)
    breaktimes = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), breaktimes))

    if form.get('inspection_version', False):
        tabel.change_for_inspection(tabel.prod_month.get('norm_work_hours', 0), workdays)

    tabel.format_cells(len(employments))
    tabel.add_main_info()

    # construct day
    tabel.construct_dates('%d', 12, 6, int)

    # construct weekday
    tabel.construct_dates('%w', 14, 6)

    # construct day 2
    tabel.construct_dates('d%d', 15, 6)

    tabel.construnts_users_info(employments, 16, 0, ['code', 'fio', 'position', 'hired'], extra_row=True)
    tabel.fill_table(workdays, employments, breaktimes, working_hours, 16, 6)
    tabel.add_xlsx_functions(len(employments), 12, 37, extra_row=True)
    tabel.add_sign(16 + len(employments) * 2 + 2)

    return workbook, 'Tabel'
