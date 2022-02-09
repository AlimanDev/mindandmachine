from datetime import date, datetime, timedelta, time
import pandas as pd
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkType
from src.base.models import Employment, Shop, WorkerPosition
from django.db import transaction


def get_dttm_end(dttm_start, hours, breaks):
    minutes = hours * 60
    for start, end, breaks in breaks:
        if minutes >= start and minutes <= end:
            minutes += sum(breaks)
            break
    
    return dttm_start + timedelta(minutes=minutes)

def create_worker_days(dttm_start, hours, breaks, created_days, last_name, dt, employment, shop, type_id=WorkerDay.TYPE_WORKDAY, work_type=None):
    dttm_end = get_dttm_end(dttm_start, float(hours), breaks)

    for start, end in created_days.get(last_name, {}).get(dt, []):
        if dttm_start == start:
            dttm_start = end + timedelta(hours=1)
            dttm_end = get_dttm_end(dttm_start, float(hours), breaks)
            break
    closest_plan_approved = WorkerDay.objects.create(
        employee_id=employment.employee_id,
        employment=employment,
        dttm_work_start=dttm_start,
        dttm_work_end=dttm_end,
        dt=dt,
        type_id=type_id,
        shop=shop,
        is_fact=False,
        is_approved=True,
    )
    worker_days = [
        closest_plan_approved,
        WorkerDay.objects.create(
            employee_id=employment.employee_id,
            employment=employment,
            dttm_work_start=dttm_start,
            dttm_work_end=dttm_end,
            dt=dt,
            type_id=type_id,
            shop=shop,
            is_fact=False,
            is_approved=False,
        )
    ] + [
        WorkerDay.objects.create(
            employee_id=employment.employee_id,
            employment=employment,
            dttm_work_start=dttm_start,
            dttm_work_end=dttm_end,
            dt=dt,
            type_id=type_id,
            shop=shop,
            is_fact=True,
            is_approved=is_approved,
            closest_plan_approved=closest_plan_approved,
        )
        for is_approved in [False, True]
    ]
    if work_type:
        WorkerDayCashboxDetails.objects.bulk_create(
            [
                WorkerDayCashboxDetails(
                    work_type=work_type,
                    worker_day=wd,
                )
                for wd in worker_days
            ]
        )
    created_days.setdefault(last_name, {}).setdefault(dt, []).append((dttm_start, dttm_end))

    return created_days

def upload_tabel(file, shop_id, number_of_days=31, month=12, year=2021):
    shop = Shop.objects.select_related('settings__breaks', 'network__breaks').get(id=shop_id)
    breaks = shop.settings.breaks.breaks if shop.settings else shop.network.breaks.breaks
    df = pd.read_excel(file, skiprows=5).fillna('')
    FIO_COL = df.columns[2]
    POS_COL = df.columns[3]
    DATES_COLS = [df.columns[i + 5] for i in range(number_of_days)]
    SD_COL = 'с/д'
    
    position_types = {w.name: w.default_work_type_names.first() for w in WorkerPosition.objects.all()}
    work_types = {w.work_type_name_id: w for w in WorkType.objects.filter(shop=shop)}

    created_days = {}

    with transaction.atomic():
        for _, row in df.iterrows():
            sd_created = False
            if not row[FIO_COL]:
                continue
            last_name = row[FIO_COL].split()[0]
            work_type = work_types[position_types[row[POS_COL]].id]
            for day in DATES_COLS:
                dt = date(year=year, month=month, day=int(day))
                value = row[day]
                if value:
                    employment = Employment.objects.get_active(
                        dt_from=dt,
                        dt_to=dt,
                        shop=shop,
                        employee__user__last_name=last_name,
                    ).first()
                    if not employment:
                        print(f'No employment for {last_name}')
                        continue
                    values = value.split('\n')
                    for value in values:
                        if 'Я' in value:
                            dttm_start = datetime.combine(dt, time(8))
                            hours = value.replace('Я', '').replace(',', '.')
                        else:
                            dttm_start = datetime.combine(dt, time(22))
                            hours = value.replace('Н', '').replace(',', '.')

                        created_days = create_worker_days(
                            dttm_start, hours, breaks, created_days, 
                            last_name, dt, employment, shop, work_type=work_type
                        )
                elif not sd_created and row[SD_COL]:
                    sd_created = True
                    employment = Employment.objects.get_active(
                        dt_from=dt,
                        dt_to=dt,
                        shop=shop,
                        employee__user__last_name=last_name,
                    ).first()
                    if not employment:
                        print(f'No employment for {last_name}')
                        continue
                    dttm_start = datetime.combine(dt, time(8))   
                    created_days = create_worker_days(
                        dttm_start, row[SD_COL], breaks, created_days, 
                        last_name, dt, employment, shop, type_id='SD',
                    )
