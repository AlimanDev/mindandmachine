from rest_framework.test import APITestCase
from src.util.urv.create_urv_stat import urv_stat_v1
from src.util.urv.urv_violators import urv_violators_report, urv_violators_report_xlsx, urv_violators_report_xlsx_v2
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

        WorkerDay.objects.create(
            worker_id=self.employment2.user_id,
            employment=self.employment2,
            shop_id=self.employment2.shop_id,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(13)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(1)),
            is_approved=True,
            type=WorkerDay.TYPE_WORKDAY,
        )
        
        WorkerDay.objects.create(
            worker_id=self.employment3.user_id,
            employment=self.employment3,
            shop_id=self.employment3.shop_id,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
            type=WorkerDay.TYPE_WORKDAY,
        )
        
        AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            dttm=datetime.combine(self.dt, time(12, 54)),
            user_id=self.employment2.user_id,
            type=AttendanceRecords.TYPE_COMING,
        )
        AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            dttm=datetime.combine(self.dt + timedelta(1), time(0, 13)),
            user_id=self.employment2.user_id,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            dttm=datetime.combine(self.dt + timedelta(1), time(0, 14)),
            user_id=self.employment2.user_id,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        AttendanceRecords.objects.create(
            shop_id=self.employment3.shop_id,
            dttm=datetime.combine(self.dt, time(8, 54)),
            user_id=self.employment3.user_id,
            type=AttendanceRecords.TYPE_COMING,
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
        data = urv_violators_report(self.network.id, dt_from=self.dt, dt_to=self.dt)
        assert_data = {
            self.employment3.user_id: {
                self.dt: {
                    'shop_id': self.employment3.shop_id, 
                    'type': 'L'
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
