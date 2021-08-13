from rest_framework.test import APITestCase
from src.reports.utils.create_urv_stat import urv_stat_v1
from src.reports.utils.urv_violators import urv_violators_report, urv_violators_report_xlsx, urv_violators_report_xlsx_v2
from src.reports.utils.unaccounted_overtime import get_unaccounted_overtimes, unaccounted_overtimes_xlsx
from src.util.test import create_departments_and_users
import pandas as pd
from datetime import date, datetime, time, timedelta
from src.timetable.models import WorkerDay, AttendanceRecords
from django.test import override_settings


@override_settings(MDA_SKIP_LEAVING_TICK=True)
class TestUrvFiles(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
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


    def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type=WorkerDay.TYPE_WORKDAY):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=employment.shop_id,
            type=type,
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
        self.network.save()
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
        # меньше часа переработка
        self._create_worker_day(
            self.employment1,
            dttm_work_start=datetime.combine(self.dt, time(13, 45)),
            dttm_work_end=datetime.combine(self.dt, time(20, 15)),
            is_approved=True,
            is_fact=True,
        )
        # переработка 3 часа
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(12)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(3)),
            is_approved=True,
            is_fact=True,
        )
        # нет переработки
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
            is_fact=True,
        )
        # переработка 1 час
        self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(7)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30)),
            is_approved=True,
            is_fact=True,
        )


    def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type=WorkerDay.TYPE_WORKDAY):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=employment.shop_id,
            type=type,
            employment=employment,
            employee=employment.employee,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
            created_by=self.user1,
        )

    def test_unaccounted_overtimes(self):
        data = get_unaccounted_overtimes(self.network.id, dt_from=self.dt, dt_to=self.dt)
        self.assertEquals(data.count(), 2)
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
        self.assertEquals(list(data.values('employee_id', 'overtime')), assert_data)

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
        self.assertEquals(dict(df.iloc[0]), data1)
        self.assertEquals(dict(df.iloc[1]), data2)


# class TestOvertimesUndertimes(APITestCase):
#     USER_USERNAME = "user1"
#     USER_EMAIL = "q@q.q"
#     USER_PASSWORD = "4242"

#     def setUp(self):
#         super().setUp()
#         create_departments_and_users(self)
#         self.dt = date.today()
#         self.network.only_fact_hours_that_in_approved_plan = True
#         self.network.save()
#         self._create_worker_day(
#             self.employment1,
#             dttm_work_start=datetime.combine(self.dt, time(14)),
#             dttm_work_end=datetime.combine(self.dt, time(20)),
#             is_approved=True,
#         )
#         self._create_worker_day(
#             self.employment2,
#             dttm_work_start=datetime.combine(self.dt, time(13)),
#             dttm_work_end=datetime.combine(self.dt + timedelta(1), time(1)),
#             is_approved=True,
#         )
#         self._create_worker_day(
#             self.employment3,
#             dttm_work_start=datetime.combine(self.dt, time(8)),
#             dttm_work_end=datetime.combine(self.dt, time(20)),
#             is_approved=True,
#         )
#         self._create_worker_day(
#             self.employment4,
#             dttm_work_start=datetime.combine(self.dt, time(8)),
#             dttm_work_end=datetime.combine(self.dt, time(20)),
#             is_approved=True,
#         )
#         # меньше часа переработка
#         self._create_worker_day(
#             self.employment1,
#             dttm_work_start=datetime.combine(self.dt, time(13, 45)),
#             dttm_work_end=datetime.combine(self.dt, time(20, 15)),
#             is_approved=True,
#             is_fact=True,
#         )
#         # переработка 3 часа
#         self._create_worker_day(
#             self.employment2,
#             dttm_work_start=datetime.combine(self.dt, time(12)),
#             dttm_work_end=datetime.combine(self.dt + timedelta(1), time(3)),
#             is_approved=True,
#             is_fact=True,
#         )
#         # нет переработки
#         self._create_worker_day(
#             self.employment3,
#             dttm_work_start=datetime.combine(self.dt, time(8)),
#             dttm_work_end=datetime.combine(self.dt, time(20)),
#             is_approved=True,
#             is_fact=True,
#         )
#         # переработка 1 час
#         self._create_worker_day(
#             self.employment4,
#             dttm_work_start=datetime.combine(self.dt, time(7)),
#             dttm_work_end=datetime.combine(self.dt, time(20, 30)),
#             is_approved=True,
#             is_fact=True,
#         )


#     def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type=WorkerDay.TYPE_WORKDAY):
#         if not dt:
#             dt = self.dt
#         return WorkerDay.objects.create(
#             shop_id=employment.shop_id,
#             type=type,
#             employment=employment,
#             employee=employment.employee,
#             dt=dt,
#             dttm_work_start=dttm_work_start,
#             dttm_work_end=dttm_work_end,
#             is_fact=is_fact,
#             is_approved=is_approved,
#             created_by=self.user1,
#         )

#     def test_unaccounted_overtimes(self):
#         data = get_unaccounted_overtimes(self.network.id, dt_from=self.dt, dt_to=self.dt)
#         self.assertEquals(data.count(), 2)
#         assert_data = [
#             {
#                 'employee_id': self.employment2.employee_id,
#                 'overtime': 3600 * 3,
#             },
#             {
#                 'employee_id': self.employment4.employee_id,
#                 'overtime': 3600 + 1800,
#             }
#         ]
#         self.assertEquals(list(data.values('employee_id', 'overtime')), assert_data)

#     def test_unaccounted_overtimes_xlsx(self):
#         data = unaccounted_overtimes_xlsx(self.network.id, dt_from=self.dt, dt_to=self.dt, in_memory=True)
#         df = pd.read_excel(data['file'])
#         df.fillna('', inplace=True)
#         self.assertEqual(len(df.iloc[:,:]), 2)
#         data1 = {
#             'Дата': self.dt.strftime('%d.%m.%Y'), 
#             'Код объекта': self.employment2.shop.code, 
#             'Название объекта': self.employment2.shop.name, 
#             'Табельный номер': self.employment2.employee.tabel_code, 
#             'ФИО': self.employment2.employee.user.get_fio(), 
#             'Неучтенные переработки': 'более 3 часов'
#         }
#         data2 = {
#             'Дата': self.dt.strftime('%d.%m.%Y'), 
#             'Код объекта': self.employment4.shop.code, 
#             'Название объекта': self.employment4.shop.name, 
#             'Табельный номер': '', 
#             'ФИО': self.employment4.employee.user.get_fio(), 
#             'Неучтенные переработки': 'более 1 часа'
#         }
#         self.assertEquals(dict(df.iloc[0]), data1)
#         self.assertEquals(dict(df.iloc[1]), data2)
