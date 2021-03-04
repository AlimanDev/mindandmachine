from src.timetable.models import WorkerDay, AttendanceRecords
from src.base.models import Shop, User, Employment
import xlsxwriter
import io
from datetime import date, datetime, timedelta
from django.db.models import Sum, Q, Count, Exists, OuterRef
from django.db.models.functions import Trunc
from dateutil.relativedelta import relativedelta

NO_RECORDS = 'R'
NO_COMMING = 'C'
NO_LEAVING = 'L'
NO_COMING_PROBABLY = 'CP'

NO_COMMING_HOURS = 4

text = {
    NO_RECORDS: 'Нет отметок',
    NO_COMMING: 'Нет отметки о приходе',
    NO_LEAVING: 'Нет отметки об уходе',
    NO_COMING_PROBABLY: 'Предположительно нет отметки о приходе',
}


def urv_violators_report(network_id, dt_from=None, dt_to=None):
    if not dt_from or not dt_to:
        dt_from = date.today() - timedelta(1)
        dt_to = date.today() - timedelta(1)
    data = {}
    user_ids = Employment.objects.get_active(
        network_id,
        dt_from=dt_from,
        dt_to=dt_to,
    ).values_list('user_id', flat=True)
    bad_records = AttendanceRecords.objects.filter(
        user_id__in=user_ids,
        dttm__date__gte=dt_from,
        dttm__date__lte=dt_to,
    ).values(
        'user_id',
        'dt',
    ).annotate(
        comming=Count('dt', filter=Q(type=AttendanceRecords.TYPE_COMING)),
        leaving=Count('dt', filter=Q(type=AttendanceRecords.TYPE_LEAVING)),
    ).filter(
        Q(comming=0) | Q(leaving=0),
    ).values(
        'user_id', 'dt', 'comming', 'leaving',
    )
    worker_days = WorkerDay.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        shop__network_id=network_id,
        type=WorkerDay.TYPE_WORKDAY,
        is_approved=True,
        is_fact=False,
        worker_id__in=user_ids,
    )
    users_wds = {}
    for wd in worker_days:
        users_wds.setdefault(wd.worker_id, {})[wd.dt] = wd
    
    for record in bad_records:
        first_key = record['user_id']
        second_key = record['dt']
        if users_wds.get(first_key, {}).get(second_key):
            t = NO_COMMING if record['comming'] == 0 else NO_LEAVING
            if t == NO_LEAVING:
                wd = users_wds.get(first_key, {}).get(second_key)
                att_record = AttendanceRecords.objects.filter(
                    dttm__date=second_key,
                    shop_id=wd.shop_id,
                    user_id=first_key,
                ).first()
                if not att_record:
                    continue
                second_cond = (att_record.dttm > wd.dttm_work_end or (att_record.dttm - wd.dttm_work_start).total_seconds() / 3600 >= NO_COMMING_HOURS)
                if att_record.dttm > wd.dttm_work_start and second_cond:
                    t = NO_COMING_PROBABLY

            data.setdefault(first_key, {})[second_key] = {
                'shop_id': wd.shop_id,
                'type': t,
            }
    
    no_records = worker_days.annotate(
        exist_records=Exists(
            AttendanceRecords.objects.filter(
                user_id=OuterRef('worker_id'),
                dttm__date=OuterRef('dt'),
            )
        )
    ).filter(
        exist_records=False,
    )
    for record in no_records:
        first_key = record.worker_id
        second_key = record.dt
        data.setdefault(first_key, {})[second_key] = {
            'shop_id': record.shop_id,
            'type': NO_RECORDS,
        } 

    return data


def urv_violators_report_xlsx(network_id, dt=None, title=None, in_memory=False):
    if not dt:
        dt = date.today() - timedelta(1)
    if not title:
        title = f'URV_violators_report_{dt}.xlsx'
    SHOP = 0
    FIO = 1
    REASON = 2
    shops = { 
        s.id: s.name for s in Shop.objects.filter(
            id__in=WorkerDay.objects.filter(
                dt=dt,
                shop__network_id=network_id,
                type=WorkerDay.TYPE_WORKDAY,
                is_approved=True,
                is_fact=False,
            ).values_list('shop_id', flat=True),
        )
    }
    data = urv_violators_report(network_id, dt_from=dt, dt_to=dt)
    users = {
        u.id: f"{u.last_name} {u.first_name}" for u in User.objects.filter(
            id__in=data.keys(),
        )
    }

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)
    
    rows = [
        {
            'shop': shops.get(reason['shop_id'], ''),
            'fio': users.get(user_id),
            'reason': text.get(reason['type']),
        }
        for user_id, record in data.items()
        for dt, reason in record.items()
    ]
    rows = sorted(rows, key=lambda x: x['shop'])

    worksheet = workbook.add_worksheet('{}'.format(dt.strftime('%Y.%m.%d')))
    def_format = {
        'border': 1,
    }
    worksheet.write(0, SHOP, 'Магазин')
    worksheet.write(0, FIO, 'ФИО')
    worksheet.write(0, REASON, 'Нарушение')
    worksheet.set_column(0, SHOP, 15)
    worksheet.set_column(0, FIO, 20)
    worksheet.set_column(0, REASON, 20)
    row = 1
    for record in rows:
        worksheet.write(row, SHOP, record['shop'])
        worksheet.write_string(row, FIO, record['fio'], workbook.add_format(def_format))
        worksheet.write_string(row, REASON, record['reason'], workbook.add_format(def_format))
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
    

def urv_violators_report_xlsx_v2(network_id, dt_from=None, dt_to=None, title=None, in_memory=False):
    if not dt_from:
        dt_from = date.today().replace(day=1)
    if not dt_to:
        dt_to = dt_from + relativedelta(day=31)
    if not title:
        title = f'URV_violators_report_{dt_from}-{dt_to}.xlsx'
    SHOP_CODE = 0
    SHOP = 1
    TABEL_CODE = 2
    FIO = 3
    POSITION = 4
    shops = { 
        s.id: s for s in Shop.objects.all()
    }
    data = urv_violators_report(network_id, dt_from=dt_from, dt_to=dt_to)

    users = {
        u.id: f"{u.last_name} {u.first_name} {u.middle_name if u.middle_name else ''}" for u in User.objects.filter(
            id__in=data.keys(),
        )
    }

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)
    
    rows = []

    for user_id, records in data.items():
        empl = Employment.objects.get_active(
            network_id,
            dt_from,
            dt_to,
            user_id=user_id,
        ).select_related('position').first()
        rows.append(
            {
                'shop': shops.get(empl.shop_id if empl else None, Shop()).name or '',
                'shop_code': shops.get(empl.shop_id if empl else None, Shop()).code or '',
                'empl': empl,
                'fio': users.get(user_id),
                'records': records, 
            }
        ) 

    rows = sorted(rows, key=lambda x: x['shop'])


    worksheet = workbook.add_worksheet('{}-{}'.format(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d')))
    def_format = {
        'border': 1,
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True,
    }
    header_format = {
        'border': 1,
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
    }
    worksheet.write_string(0, SHOP_CODE, 'Код магазина', workbook.add_format(header_format))
    worksheet.write_string(0, SHOP, 'Магазин', workbook.add_format(header_format))
    worksheet.write_string(0, TABEL_CODE, 'Табельный номер', workbook.add_format(header_format))
    worksheet.write_string(0, FIO, 'ФИО', workbook.add_format(header_format))
    worksheet.write_string(0, POSITION, 'Должность', workbook.add_format(header_format))
    worksheet.set_column(SHOP_CODE, SHOP_CODE, 15)
    worksheet.set_column(SHOP, SHOP, 15)
    worksheet.set_column(FIO, FIO, 20)
    worksheet.set_column(POSITION, POSITION, 20)
    worksheet.set_column(TABEL_CODE, TABEL_CODE, 15)
    dates = [dt_from + timedelta(i) for i in range((dt_to - dt_from).days + 1)]
    col = POSITION
    for dt in dates:
        col += 1
        worksheet.write_string(0, col, dt.strftime('%d.%m.%Y'), workbook.add_format(header_format))
        worksheet.set_column(col, col, 10)
    row = 1
    for record in rows:
        worksheet.write_string(row, SHOP_CODE, record['shop_code'] or '', workbook.add_format(def_format))
        worksheet.write_string(row, SHOP, record['shop'], workbook.add_format(def_format))
        worksheet.write_string(row, TABEL_CODE, record['empl'].tabel_code or '' if record['empl'] else '', workbook.add_format(def_format))
        worksheet.write_string(row, FIO, record['fio'], workbook.add_format(def_format))
        worksheet.write_string(row, POSITION, record['empl'].position.name if record['empl'] and record['empl'].position else '', workbook.add_format(def_format))
        col = POSITION
        for dt in dates:
            col += 1
            worksheet.write_string(row, col, text.get(record['records'].get(dt, {}).get('type', ''), ''), workbook.add_format(def_format))
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
