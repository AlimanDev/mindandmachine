from datetime import date, timedelta, datetime

import pandas as pd

from src.base.models import (
    User,
    Employee,
    ShiftSchedule,
    ShiftScheduleInterval,
)
from src.base.shift_schedule.serializers import (
    ShiftScheduleSerializer,
    ShiftScheduleIntervalSerializer,
)
from src.timetable.models import WorkerDay

DAY_TYPE_MAPPING = {
    'Больничный': WorkerDay.TYPE_SICK,
    'Выходные дни': WorkerDay.TYPE_HOLIDAY,
    'Командировка': WorkerDay.TYPE_BUSINESS_TRIP,
    'Неявки по невыясненным причинам': WorkerDay.TYPE_ABSENSE,
    'Ночные часы': WorkerDay.TYPE_WORKDAY,
    'Явка': WorkerDay.TYPE_WORKDAY,
    'Отпуск': WorkerDay.TYPE_VACATION,
    'Отпуск по уходу за ребенком': WorkerDay.TYPE_MATERNITY,  # ОЖ
    'Отпуск по беременности и родам': WorkerDay.TYPE_MATERNITY,  # вообще другой тип (Р)
    'Отпуск неоплачиваемый с разрешения работодателя': WorkerDay.TYPE_SELF_VACATION,
}


def load_shift_schedule(filepath, from_dt=None, load_employee_shift_schedules=False):
    with open(filepath, 'rb') as f:
        df = pd.read_excel(f)
        df.drop(df[df['ВидУчетаВремени'] == 'Рабочее время'].index, inplace=True)
        df['Дата'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S').dt.date
        df.drop(df[df['Дата'] < (from_dt or date.today().replace(day=1))].index, inplace=True)
        existing_employee_tabel_codes = list(
            Employee.objects.filter(employments__isnull=False).values_list('tabel_code', flat=True))
        shift_schedules_data = {}
        for idx, row in df.iterrows():
            if row['ЭтоСотрудник'] == 'Истина' and not load_employee_shift_schedules:
                continue

            if row['ЭтоСотрудник'] == 'Истина' and row['ГрафикРаботы'] not in existing_employee_tabel_codes:
                continue
            shift_schedule_data = shift_schedules_data.setdefault(row['ГУИДГрафика'], {})
            shift_schedule_data.setdefault('name', row['ГрафикРаботы'])
            shift_schedule_data.setdefault('code', row['ГУИДГрафика'])
            if row['ЭтоСотрудник'] == 'Истина':
                shift_schedule_data.setdefault('employee__tabel_code', row['ГУИДГрафика'])
            days_data = shift_schedule_data.setdefault('days', {})
            day_data = days_data.setdefault(str(row['Дата']), {})
            day_data['work_hours'] = day_data.get('work_hours', 0) + row['ДополнительноеЗначение']
            if row['ВидУчетаВремени'] == 'Явка':
                day_data['day_hours'] = day_data.get('day_hours', 0) + row['ДополнительноеЗначение']
            if row['ВидУчетаВремени'] == 'Ночные часы':
                day_data['night_hours'] = day_data.get('night_hours', 0) + row['ДополнительноеЗначение']
            day_data.setdefault('day_type', DAY_TYPE_MAPPING[row['ВидУчетаВремени']])
            day_data.setdefault('code', row['ГУИДГрафика'] + '_' + str(row['Дата']))

        shift_schedules_data_list = []
        for shift_schedule_data in shift_schedules_data.values():
            days_dict = shift_schedule_data.pop('days')
            for dt, day_dict in days_dict.items():
                day_dict['dt'] = str(dt)
                shift_schedule_data.setdefault('days', []).append(day_dict)
            shift_schedules_data_list.append(shift_schedule_data)

        fake_requset = lambda: None
        fake_requset.user = User.objects.filter(is_superuser=True).first()
        s = ShiftScheduleSerializer(data=shift_schedules_data_list, context={'request': fake_requset}, many=True)
        s.is_valid(raise_exception=True)
        ShiftSchedule.batch_update_or_create(
            data=s.validated_data,
            update_key_field='code',
            delete_scope_fields_list=['code']
        )


def load_shift_schedule_intervals(filepath):
    with open(filepath, 'rb') as f:

        df = pd.read_excel(f)
        existing_employee_tabel_codes = list(
            Employee.objects.filter(employments__isnull=False).values_list('tabel_code', flat=True))
        shift_schedule_intervals_data = []
        for idx, row in df.iterrows():
            if row['ГУИДГрафика'] == '00000000-0000-0000-0000-000000000000':
                continue

            if row['ГУИДСотрудника'] not in existing_employee_tabel_codes:
                continue

            shift_schedule_intervals_data.append({
                "code": row['ГУИДГрафика'] + '_' + row['ГУИДСотрудника'] + '_' + str(row['ДатаНачала']),
                "dt_start": datetime.strptime(row['ДатаНачала'], '%d.%m.%Y %H:%M:%S').date(),
                "dt_end": datetime.strptime(row['ДатаОкончания'], '%d.%m.%Y %H:%M:%S').date() - timedelta(days=1),
                "employee__tabel_code": row['ГУИДСотрудника'],
                "shift_schedule__code": row['ГУИДГрафика'],
            })

        fake_requset = lambda: None
        fake_requset.user = User.objects.filter(is_superuser=True).first()
        s = ShiftScheduleIntervalSerializer(data=shift_schedule_intervals_data, context={'request': fake_requset},
                                            many=True)
        s.is_valid(raise_exception=True)
        ShiftScheduleInterval.batch_update_or_create(
            data=s.validated_data,
            update_key_field='code',
            delete_scope_fields_list=['employee_id']
        )
