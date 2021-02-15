from rest_framework.test import APITestCase
from src.util.urv.create_urv_stat import main
from src.util.urv.urv_violators import urv_violators_report, urv_violators_report_xlsx
from src.util.test import create_departments_and_users
import pandas as pd
from datetime import date, datetime, time
from src.timetable.models import WorkerDay, AttendanceRecords


class TestUrvFiles(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.dt = date.today()

        for e in [self.employment2, self.employment3]:
            WorkerDay.objects.create(
                worker_id=e.user_id,
                employment=e,
                shop_id=e.shop_id,
                dt=self.dt,
                dttm_work_start=datetime.combine(self.dt, time(8)),
                dttm_work_end=datetime.combine(self.dt, time(20)),
                is_approved=True,
                type=WorkerDay.TYPE_WORKDAY,
            )
        
        AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            dttm=datetime.combine(self.dt, time(7, 54)),
            user_id=self.employment2.user_id,
            type=AttendanceRecords.TYPE_COMING,
        )
        AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            dttm=datetime.combine(self.dt, time(20, 13)),
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
        data = main(self.dt, self.dt, network_id=self.network.id, in_memory=True)
        df = pd.read_excel(data['file'])
        self.assertEqual(len(df.iloc[:,:]), 1)
        data = {
            'Магазин': 'Shop1', 
            'Дата': self.dt.strftime('%d.%m.%Y'), 
            'Плановое кол-во отметок, ПРИХОД': 2, 
            'Фактическое кол-во отметок, ПРИХОД': 2, 
            'Разница, ПРИХОД': 0, 
            'Плановое кол-во отметок, УХОД': 2, 
            'Фактическое кол-во отметок, УХОД': 1, 
            'Разница, УХОД': 1, 
            'Плановое кол-во часов': '21:30:00', 
            'Фактическое кол-во часов': '11:04:00', 
            'Разница, ЧАСЫ': '10:26:00'
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
        df = pd.read_excel(data['file'])
        data = {
            'Магазин': 'Shop1', 
            'ФИО': 'Сидоров Иван3', 
            'Нарушение': 'Нет отметки об уходе'
        }
        self.assertEqual(len(df.iloc[:,:]), 1)
        self.assertEqual(dict(df.iloc[0]), data)
