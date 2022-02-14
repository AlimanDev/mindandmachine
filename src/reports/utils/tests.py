from django.db.models.aggregates import Sum
from django.db.models.fields import FloatField
from django.db.models.functions.comparison import Coalesce
from django.db.models.query_utils import Q
from src.reports.helpers import RoundWithPlaces
from src.reports.utils.pivot_tabel import PlanAndFactPivotTabel
from src.util.dg.helpers import MONTH_NAMES
from dateutil.relativedelta import relativedelta
from src.base.models import Employee, ProductionDay
from src.reports.utils.overtimes_undertimes import overtimes_undertimes, overtimes_undertimes_xlsx
from rest_framework.test import APITestCase
from src.reports.utils.create_urv_stat import urv_stat_v1
from src.reports.utils.urv_violators import urv_violators_report, urv_violators_report_xlsx, urv_violators_report_xlsx_v2
from src.reports.utils.unaccounted_overtime import get_unaccounted_overtimes, unaccounted_overtimes_xlsx
from src.util.test import create_departments_and_users
import pandas as pd
from datetime import date, datetime, time, timedelta
from src.timetable.models import PlanAndFactHours, ProdCal, WorkerDay, AttendanceRecords
from django.test import override_settings


class TestUrvFiles(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'I': 'магазин',
                    'R': 'магазина',
                    'P': 'магазине',
                }
            }
        )
        self.network.save()
        self.dt = date.today()
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(13)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(1)),
            is_approved=True,
        )
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        self._create_att_record(
            self.employment2,
            datetime.combine(self.dt, time(12, 54)),
            AttendanceRecords.TYPE_COMING,
        )
        self._create_att_record(
            self.employment2,
            datetime.combine(self.dt + timedelta(1), time(0, 13)),
            AttendanceRecords.TYPE_LEAVING,
        )
        self._create_att_record(
            self.employment2,
            datetime.combine(self.dt + timedelta(1), time(0, 14)),
            AttendanceRecords.TYPE_LEAVING,
        )
        self._create_att_record(
            self.employment3,
            datetime.combine(self.dt, time(8, 54)),
            AttendanceRecords.TYPE_COMING,
        )
        self.network.skip_leaving_tick = True
        self.network.save()

    def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type_id=WorkerDay.TYPE_WORKDAY):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=employment.shop_id,
            type_id=type_id,
            employment=employment,
            employee=employment.employee,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
            created_by=self.user1,
        )

    def _create_att_record(self, employment, dttm, type):
        return AttendanceRecords.objects.create(
            shop_id=employment.shop_id,
            user_id=employment.employee.user_id,
            dttm=dttm,
            type=type,
        )

    def test_urv_stat(self):
        data = urv_stat_v1(self.dt, self.dt, network_id=self.network.id, in_memory=True)
        df = pd.read_excel(data['file'])
        self.assertEqual(len(df.iloc[:,:]), 1)
        data = {
            'Магазин': 'Shop1', 
            'Дата': self.dt.strftime('%d.%m.%Y'), 
            'Кол-во отметок план, ПРИХОД': 2, 
            'Опоздания': 1,
            'Ранний уход': 1,
            'Кол-во отметок факт, ПРИХОД': 2, 
            'Разница, ПРИХОД': 0, 
            'Кол-во отметок план, УХОД': 2, 
            'Кол-во отметок факт, УХОД': 1, 
            'Разница, УХОД': 1, 
            'Кол-во часов план': '21:30:00', 
            'Кол-во часов факт': '10:05:00', 
            'Разница, ЧАСЫ': '11:25:00',
            'Разница, ПРОЦЕНТЫ': '47%',
        }
        self.assertEqual(dict(df.iloc[0]), data)

    def test_urv_violators_report(self):
        self._create_att_record(
            self.employment4,
            datetime.combine(self.dt, time(8, 45)),
            AttendanceRecords.TYPE_COMING,
        )
        data = urv_violators_report(self.network.id, dt_from=self.dt, dt_to=self.dt, exclude_created_by=True)
        assert_data = {
            self.employment2.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['ED']
                }
            },
            self.employment3.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['L', 'LA']
                }
            },
            self.employment4.employee_id: {
                self.dt: {
                    'shop_id': self.employment4.shop_id, 
                    'types': ['L', 'BF']
                }
            }
        }
        self.assertEqual(data, assert_data)

    def test_urv_violators_report_in_time(self):
        self._create_att_record(
            self.employment2,
            datetime.combine(self.dt + timedelta(1), time(1)),
            AttendanceRecords.TYPE_LEAVING,
        )
        data = urv_violators_report(self.network.id, dt_from=self.dt, dt_to=self.dt, exclude_created_by=True)
        assert_data = {
            self.employment3.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['L', 'LA']
                }
            },
        }
        self.assertEqual(data, assert_data)

    def test_urv_violators_report_exclude_created_by(self):
        self._create_att_record(
            self.employment4,
            datetime.combine(self.dt, time(8, 45)),
            AttendanceRecords.TYPE_COMING,
        )
        WorkerDay.objects.filter(
            employee_id=self.employment4.employee_id,
            is_fact=True,
            is_approved=True,
        ).delete()
        self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(8, 45)),
            dttm_work_end=datetime.combine(self.dt, time(19)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment5,
            dttm_work_start=datetime.combine(self.dt, time(9)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        self._create_worker_day(
            self.employment5,
            dttm_work_start=datetime.combine(self.dt, time(7, 45)),
            dttm_work_end=datetime.combine(self.dt, time(18, 3)),
            is_approved=True,
            is_fact=True,
        )
        data = urv_violators_report(self.network.id, dt_from=self.dt, dt_to=self.dt, exclude_created_by=True)
        assert_data = {
            self.employment2.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['ED']
                }
            },
            self.employment3.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['L', 'LA']
                }
            },
            self.employment4.employee_id: {
                self.dt: {
                    'shop_id': self.employment4.shop_id, 
                    'types': ['L', 'BF']
                }
            },
            self.employment5.employee_id: {
                self.dt: {
                    'shop_id': self.employment5.shop_id, 
                    'types': ['R']
                }
            }
        }
        self.assertEqual(data, assert_data)
        data = urv_violators_report(self.network.id, dt_from=self.dt, dt_to=self.dt)
        assert_data = {
            self.employment2.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['ED']
                }
            },
            self.employment3.employee_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'types': ['L', 'LA']
                }
            },
            self.employment4.employee_id: {
                self.dt: {
                    'shop_id': self.employment4.shop_id, 
                    'types': ['BF']
                }
            },
            self.employment5.employee_id: {
                self.dt: {
                    'shop_id': self.employment5.shop_id, 
                    'types': ['ED']
                }
            }
        }
        self.assertEqual(data, assert_data)


    def test_urv_violators_report_xlsx(self):
        self.network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'R': 'объекта',
                }
            }
        )
        self.network.save()
        data = urv_violators_report_xlsx(self.network.id, dt_from=self.dt, dt_to=self.dt, in_memory=True)
        df = pd.read_excel(data['file']).fillna('')
        data1 = {
            'Дата': self.dt.strftime('%d.%m.%Y'),
            'Код объекта': self.shop.code,
            'Название объекта': self.shop.name, 
            'Табельный номер': '',
            'ФИО': 'Сидоров Иван3', 
            'Нарушение': 'Нет ухода\nОпоздание'
        }
        data2 = {
            'Дата': self.dt.strftime('%d.%m.%Y'),
            'Код объекта': self.shop.code,
            'Название объекта': self.shop.name, 
            'Табельный номер': 'employee2_tabel_code',
            'ФИО': 'Иванов Иван2', 
            'Нарушение': 'Ранний уход'
        }
        self.assertEqual(len(df.iloc[:,:]), 2)
        self.assertEqual(dict(df.iloc[0]), data1)
        self.assertEqual(dict(df.iloc[1]), data2)


    def test_urv_violators_report_xlsx_v2(self):
        data = urv_violators_report_xlsx_v2(self.network.id, dt_from=self.dt, in_memory=True)
        df = pd.read_excel(data['file'])
        df.fillna('', inplace=True)
        data = {
            'Код магазина': self.shop.code, 
            'Магазин': 'Shop1', 
            'Табельный номер': '', 
            'ФИО': 'Сидоров Иван3', 
            'Должность': '',
            self.dt.strftime('%d.%m.%Y'): 'Нет ухода\nОпоздание'
        }
        self.assertEqual(len(df.iloc[:,:]), 2)
        self.assertEqual(dict(df.iloc[0, :6]), data)


class TestUnaccountedOvertime(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.dt = date.today()
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'I': 'объект',
                    'R': 'объекта',
                    'P': 'объекте',
                }
            }
        )
        self.network.save()
        pa1 = self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt, time(14)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        pa2 = self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(13)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(1)),
            is_approved=True,
        )
        pa3 = self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        pa4 = self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        # меньше часа переработка
        self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt, time(13, 45)),
            dttm_work_end=datetime.combine(self.dt, time(20, 15)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa1.id,
        )
        # переработка 3 часа
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(12)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(3)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa2.id,
        )
        # нет переработки
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa3.id,
        )
        # переработка 1 час
        self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(7)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa4.id,
        )


    def _create_worker_day(
            self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type_id=WorkerDay.TYPE_WORKDAY, closest_plan_approved_id=None):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=employment.shop_id,
            type_id=type_id,
            employment=employment,
            employee=employment.employee,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
            created_by=self.user1,
            closest_plan_approved_id=closest_plan_approved_id,
        )

    def test_unaccounted_overtimes(self):
        data = get_unaccounted_overtimes(self.network.id, dt_from=self.dt, dt_to=self.dt)
        self.assertEqual(data.count(), 2)
        assert_data = [
            {
                'employee_id': self.employment2.employee_id,
                'overtime': 3600 * 3,
            },
            {
                'employee_id': self.employment4.employee_id,
                'overtime': 3600 + 1800,
            }
        ]
        self.assertEqual(list(data.values('employee_id', 'overtime')), assert_data)

    def test_unaccounted_overtimes_xlsx(self):
        data = unaccounted_overtimes_xlsx(self.network.id, dt_from=self.dt, dt_to=self.dt, in_memory=True)
        df = pd.read_excel(data['file'])
        df.fillna('', inplace=True)
        self.assertEqual(len(df.iloc[:,:]), 2)
        data1 = {
            'Дата': self.dt.strftime('%d.%m.%Y'), 
            'Код объекта': self.employment2.shop.code, 
            'Название объекта': self.employment2.shop.name, 
            'Табельный номер': self.employment2.employee.tabel_code, 
            'ФИО': self.employment2.employee.user.get_fio(), 
            'Неучтенные переработки': 'более 3 часов'
        }
        data2 = {
            'Дата': self.dt.strftime('%d.%m.%Y'), 
            'Код объекта': self.employment4.shop.code, 
            'Название объекта': self.employment4.shop.name, 
            'Табельный номер': '', 
            'ФИО': self.employment4.employee.user.get_fio(), 
            'Неучтенные переработки': 'более 1 часа'
        }
        self.assertEqual(dict(df.iloc[0]), data1)
        self.assertEqual(dict(df.iloc[1]), data2)


class TestOvertimesUndertimes(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.dt = date.today()
        self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt, time(14)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(13)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(1)),
            is_approved=True,
        )
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt, time(13, 45)),
            dttm_work_end=datetime.combine(self.dt, time(20, 15)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(12)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(3)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(7)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30)),
            is_approved=True,
            is_fact=True,
        )


    def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type_id=WorkerDay.TYPE_WORKDAY):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=employment.shop_id,
            type_id=type_id,
            employment=employment,
            employee=employment.employee,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
            created_by=self.user1,
        )

    def _test_accounting_period(self, period_step):
        data = overtimes_undertimes(period_step=period_step)
        self.network.accounting_period_length = period_step
        dt_from, dt_to = self.network.get_acc_period_range(date.today())
        self.assertEqual(data['months'], [(dt_from + relativedelta(months=i)).month for i in range(period_step)])
        self.assertCountEqual(list(data['data'].values())[0].keys(), [(dt_from + relativedelta(months=i)).month for i in range(period_step)] + ['plan_sum', 'fact_sum', 'norm_sum'])
        return data

    def _test_accounting_period_xlsx(self, period_step):
        data = overtimes_undertimes_xlsx(period_step=period_step, in_memory=True)
        df = pd.read_excel(data['file'])
        df.fillna('', inplace=True)
        self.assertEqual(len(df.columns[6:]), period_step * 5)
        return df

    def _get_norm_for_month(self, date):
        return ProdCal.objects.filter(
            dt__month=date.month,
            dt__year=date.year,
        ).exclude(
            dt__in=ProductionDay.objects.filter(dt__month=date.month, is_celebration=True).values_list('dt', flat=True)
        ).values('dt').distinct().aggregate(
            plan=Coalesce(
                RoundWithPlaces(
                    Sum(
                        'norm_hours',
                        output_field=FloatField(),
                    ), 
                    1,
                    output_field=FloatField(),
                ),
                0.0
            ),
        )['plan']

    def _get_norm_for_period(self, dt_from, dt_to):
        return ProdCal.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
        ).exclude(
            dt__in=ProductionDay.objects.filter(dt__gte=dt_from, dt__lte=dt_to, is_celebration=True).values_list('dt', flat=True)
        ).values('dt').distinct().aggregate(
            plan=Coalesce(
                RoundWithPlaces(
                    Sum(
                        'norm_hours',
                        output_field=FloatField(),
                    ), 
                    1,
                    output_field=FloatField(),
                ),
                0.0
            ),
        )['plan']

    def test_overtimes_undertimes(self):
        data = self._test_accounting_period(3)
        plan_sum = self._get_norm_for_period(*self.network.get_acc_period_range(date.today()))
        plan = self._get_norm_for_month(date.today())
        self.assertCountEqual(data['employees'], Employee.objects.all())
        self.assertEqual(data['data'][self.employee1.id]['plan_sum'], 5.5)
        self.assertEqual(data['data'][self.employee1.id]['fact_sum'], 5.5)
        self.assertEqual(data['data'][self.employee1.id]['norm_sum'], plan_sum)
        self.assertEqual(data['data'][self.employee1.id][date.today().month], {'plan': 5.5, 'fact': 5.5, 'norm': plan, 'fact_celebration': 0.0, 'norm_celebration': 0.0})
        self.assertEqual(data['data'][self.employee2.id]['plan_sum'], 10.8)
        self.assertEqual(data['data'][self.employee2.id]['fact_sum'], 13.8)
        self.assertEqual(data['data'][self.employee2.id]['norm_sum'], plan_sum)
        self.assertEqual(data['data'][self.employee2.id][date.today().month], {'plan': 10.8, 'fact': 13.8, 'norm': plan, 'fact_celebration': 0.0, 'norm_celebration': 0.0})
        self.assertEqual(data['data'][self.employee3.id]['plan_sum'], 10.8)
        self.assertEqual(data['data'][self.employee3.id]['fact_sum'], 10.8)
        self.assertEqual(data['data'][self.employee3.id]['norm_sum'], plan_sum)
        self.assertEqual(data['data'][self.employee3.id][date.today().month], {'plan': 10.8, 'fact': 10.8, 'norm': plan, 'fact_celebration': 0.0, 'norm_celebration': 0.0})
        self.assertEqual(data['data'][self.employee4.id]['plan_sum'], 10.8)
        self.assertEqual(data['data'][self.employee4.id]['fact_sum'], 12.3)
        self.assertEqual(data['data'][self.employee4.id]['norm_sum'], plan_sum)
        self.assertEqual(data['data'][self.employee4.id][date.today().month], {'plan': 10.8, 'fact': 12.3, 'norm': plan, 'fact_celebration': 0.0, 'norm_celebration': 0.0})
        self._test_accounting_period(1)
        self._test_accounting_period(6)
        self._test_accounting_period(12)

    def test_overtimes_undertimes_celebration_accounted_in_other_column(self):
        self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt - timedelta(1), time(12, 45)),
            dttm_work_end=datetime.combine(self.dt - timedelta(1), time(18, 10)),
            dt=self.dt - timedelta(1),
            is_approved=True,
            is_fact=True,
        )
        data = self._test_accounting_period(12)
        self.assertEqual(data['data'][self.employee1.id]['plan_sum'], 5.5)
        self.assertEqual(data['data'][self.employee1.id]['fact_sum'], 10.4) # может падать 1 января
        ProductionDay.objects.filter(dt=self.dt - timedelta(1)).update(is_celebration=True)
        data = self._test_accounting_period(12)
        self.assertEqual(data['data'][self.employee1.id]['plan_sum'], 5.5)
        self.assertEqual(data['data'][self.employee1.id]['fact_sum'], 5.5)
        month = date.today().month if not date.today().day == 1 else date.today().month - 1
        self.assertEqual(data['data'][self.employee1.id][month]['fact_celebration'], 4.9)

    def test_overtimes_undertimes_xlsx(self):
        self.maxDiff = None
        data = self._test_accounting_period_xlsx(1)
        self.network.accounting_period_length = 1
        plan_sum = self._get_norm_for_period(*self.network.get_acc_period_range(date.today()))
        plan = self._get_norm_for_month(date.today())
        assert_data = [
            {
                'ФИО': '', 
                'Табельный номер': '', 
                'Норма за учетный период': '', 
                f'Отработано на сегодня ({date.today().strftime("%d.%m.%Y")})': '', 
                f'Всего переработки/недоработки ({date.today().strftime("%d.%m.%Y")})': '', 
                'Unnamed: 5': '', 
                'Норма часов': MONTH_NAMES[date.today().month], 
                'Отработано часов': MONTH_NAMES[date.today().month], 
                'Всего переработки/недоработки':MONTH_NAMES[date.today().month], 
                'Переработки/недоработки: отработано часов в праздники':MONTH_NAMES[date.today().month], 
                'Плановое количество часов': MONTH_NAMES[date.today().month], 
            }, 
            {
                'ФИО': 'Васнецов Иван', 
                'Табельный номер': '', 
                'Норма за учетный период': plan_sum, 
                f'Отработано на сегодня ({date.today().strftime("%d.%m.%Y")})': 5.5, 
                f'Всего переработки/недоработки ({date.today().strftime("%d.%m.%Y")})': 5.5 - plan, 
                'Unnamed: 5': '', 
                'Норма часов': f'{plan}', 
                'Отработано часов': '5.5', 
                'Всего переработки/недоработки': f'{5.5 - plan}', 
                'Переработки/недоработки: отработано часов в праздники': '0.0', 
                'Плановое количество часов': '5.5'
            }, 
            {
                'ФИО': 'Иванов Иван2', 
                'Табельный номер': 'employee2_tabel_code', 
                'Норма за учетный период': plan_sum, 
                f'Отработано на сегодня ({date.today().strftime("%d.%m.%Y")})': 13.8, 
                f'Всего переработки/недоработки ({date.today().strftime("%d.%m.%Y")})': 13.8 - plan, 
                'Unnamed: 5': '', 
                'Норма часов': f'{plan}', 
                'Отработано часов': '13.8', 
                'Всего переработки/недоработки': f'{13.8 - plan}', 
                'Переработки/недоработки: отработано часов в праздники': '0.0',
                'Плановое количество часов': '10.8'
            }, 
            {
                'ФИО': 'Сидоров Иван3', 
                'Табельный номер': '', 
                'Норма за учетный период': plan_sum, 
                f'Отработано на сегодня ({date.today().strftime("%d.%m.%Y")})': 10.8, 
                f'Всего переработки/недоработки ({date.today().strftime("%d.%m.%Y")})': 10.8 - plan, 
                'Unnamed: 5': '', 
                'Норма часов': f'{plan}', 
                'Отработано часов': '10.8', 
                'Всего переработки/недоработки': f'{10.8 - plan}', 
                'Переработки/недоработки: отработано часов в праздники': '0.0',
                'Плановое количество часов': '10.8'
            }, 
            {
                'ФИО': 'Петров Иван4', 
                'Табельный номер': '', 
                'Норма за учетный период': plan_sum, 
                f'Отработано на сегодня ({date.today().strftime("%d.%m.%Y")})': 12.3, 
                f'Всего переработки/недоработки ({date.today().strftime("%d.%m.%Y")})': 12.3 - plan, 
                'Unnamed: 5': '', 
                'Норма часов': f'{plan}', 
                'Отработано часов': '12.3', 
                'Всего переработки/недоработки': f'{12.3 - plan}',
                'Переработки/недоработки: отработано часов в праздники': '0.0', 
                'Плановое количество часов': '10.8'
            }
        ]
        self.assertCountEqual(
            data[
                data['ФИО'].isin(['', 'Васнецов Иван', 'Иванов Иван2', 'Сидоров Иван3', 'Петров Иван4'])
            ].to_dict('records')[:5], 
            assert_data,
        )
        self._test_accounting_period_xlsx(3)
        self._test_accounting_period_xlsx(6)
        self._test_accounting_period_xlsx(12)


class TestPivotTabel(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.dt = date.today()

        self.employee1.tabel_code = 'employee1_tabel_code'
        self.employee3.tabel_code = 'employee3_tabel_code'
        self.employee4.tabel_code = 'employee4_tabel_code'
        self.employee1.save()
        self.employee3.save()
        self.employee4.save()   

        self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt, time(13, 45)),
            dttm_work_end=datetime.combine(self.dt, time(20, 15)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(12)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(3)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
            is_fact=True,
        )
        self._create_worker_day(
            self.employment4,
            dt=self.dt + timedelta(1),
            dttm_work_start=datetime.combine(self.dt + timedelta(1), time(7)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(20, 30)),
            is_approved=True,
            is_fact=True,
        )

    def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type_id=WorkerDay.TYPE_WORKDAY):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=employment.shop_id,
            type_id=type_id,
            employment=employment,
            employee=employment.employee,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
            created_by=self.user1,
        )

    def test_pivot_tabel(self):
        pt = PlanAndFactPivotTabel()
        table = pt.get_pivot_file(dt__gte=self.dt, dt__lte=self.dt + timedelta(1))
        df = pd.read_excel(table)
        self.assertEqual(len(df.columns), 8)
        self.assertEqual(len(df.values), 5)
        self.assertEqual(list(df.iloc[0, 5:].values), [13.75, 0.00, 13.75])
        self.assertEqual(list(df.iloc[1, 5:].values), [10.75, 0.00, 10.75])
        self.assertEqual(list(df.iloc[2, 5:].values), [0.00, 12.25, 12.25])
        self.assertEqual(list(df.iloc[3, 5:].values), [5.50, 0.00, 5.50])
        self.assertEqual(list(df.iloc[4, 5:].values), [30.00, 12.25, 42.25])
