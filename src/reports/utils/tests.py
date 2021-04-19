from rest_framework.test import APITestCase
from src.reports.utils.create_urv_stat import urv_stat_v1
from src.reports.utils.urv_violators import urv_violators_report, urv_violators_report_xlsx, urv_violators_report_xlsx_v2
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
            worker_id=employment.user_id,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
        )

    def _create_att_record(self, employment, dttm, type):
        return AttendanceRecords.objects.create(
            shop_id=employment.shop_id,
            user_id=employment.user_id,
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
            self.employment3.user_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'type': 'L'
                }
            },
            self.employment4.user_id: {
                self.dt: {
                    'shop_id': self.employment4.shop_id, 
                    'type': 'BFL'
                }
            }
        }
        self.assertEqual(data, assert_data)

    
    def test_urv_violators_report_exclude_created_by(self):
        self._create_att_record(
            self.employment4,
            datetime.combine(self.dt, time(8, 45)),
            AttendanceRecords.TYPE_COMING,
        )
        WorkerDay.objects.filter(
            worker_id=self.employment4.user_id,
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
            self.employment3.user_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'type': 'L'
                }
            },
            self.employment4.user_id: {
                self.dt: {
                    'shop_id': self.employment4.shop_id, 
                    'type': 'BFL'
                }
            },
            self.employment5.user_id: {
                self.dt: {
                    'shop_id': self.employment5.shop_id, 
                    'type': 'R'
                }
            }
        }
        data = urv_violators_report(self.network.id, dt_from=self.dt, dt_to=self.dt)
        assert_data = {
            self.employment3.user_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'type': 'L'
                }
            },
            self.employment4.user_id: {
                self.dt: {
                    'shop_id': self.employment4.shop_id, 
                    'type': 'BF'
                }
            }
        }
        self.assertEqual(data, assert_data)


    def test_urv_violators_report_xlsx(self):
        data = urv_violators_report_xlsx(self.network.id, dt=self.dt, in_memory=True)
        df = pd.read_excel(data['file']).fillna('')
        data = {
            'Код объекта': self.shop.code,
            'Название объекта': self.shop.name, 
            'Табельный номер': '',
            'ФИО': 'Сидоров Иван3 ', 
            'Нарушение': 'Нет ухода'
        }
        self.assertEqual(len(df.iloc[:,:]), 1)
        self.assertEqual(dict(df.iloc[0]), data)


    def test_urv_violators_report_xlsx_v2(self):
        data = urv_violators_report_xlsx_v2(self.network.id, dt_from=self.dt, in_memory=True)
        df = pd.read_excel(data['file'])
        df.fillna('', inplace=True)
        data = {
            'Код магазина': self.shop.code, 
            'Магазин': 'Shop1', 
            'Табельный номер': '', 
            'ФИО': 'Сидоров Иван3 ', 
            'Должность': '',
            self.dt.strftime('%d.%m.%Y'): 'Нет ухода'
        }
        self.assertEqual(len(df.iloc[:,:]), 1)
        self.assertEqual(dict(df.iloc[0, :6]), data)
