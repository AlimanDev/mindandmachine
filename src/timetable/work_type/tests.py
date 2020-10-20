from datetime import datetime, timedelta, time

from dateutil.relativedelta import relativedelta
from rest_framework import status
from rest_framework.test import APITestCase

from etc.scripts.fill_calendar import main
from src.forecast.models import OperationType, PeriodClients, OperationTypeName
from src.timetable.models import (
    WorkTypeName,
    WorkType,
    WorkerDay,
    WorkerDayCashboxDetails,
)
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


class TestWorkType(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/work_type/'

        create_departments_and_users(cls)
        cls.shop.forecast_step_minutes = time(hour=1)
        cls.shop.save()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.work_type2 = WorkType.objects.create(shop=cls.shop2, work_type_name=cls.work_type_name1)
        cls.work_type_name2 = WorkTypeName.objects.create(
            name='Тип_кассы_2',
        )
        cls.work_type3 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name2)
        cls.work_type_name3 = WorkTypeName.objects.create(
            name='Тип_кассы_3',
            code='25',
        )
        cls.work_type_name4 = WorkTypeName.objects.create(
            name='тип_кассы_4',
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.work_type1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.work_type1.id,
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id, 
            'work_type_name': {
                'id': self.work_type_name1.id,
                'name': self.work_type_name1.name,
                'code': self.work_type_name1.code,
            },
        }
        self.assertEqual(response.json(), data)

    def test_create_with_code(self):
        data = {
            'code': self.work_type_name3.code,
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        work_type = response.json()
        data['id'] = work_type['id']
        data['work_type_name'] = {
            'id': self.work_type_name3.id,
            'code': self.work_type_name3.code,
            'name': self.work_type_name3.name,
        }
        data.pop('code')
        self.assertEqual(work_type, data)

    def test_create_with_id(self):
        data = {
            'work_type_name_id': self.work_type_name3.id,
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        work_type = response.json()
        data['id'] = work_type['id']
        data['work_type_name'] = {
            'id': self.work_type_name3.id,
            'code': self.work_type_name3.code,
            'name': self.work_type_name3.name,
        }
        data.pop('work_type_name_id')
        self.assertEqual(work_type, data)

    def test_update_by_code(self):
        data = {
            'min_workers_amount': 30,
            'code': self.work_type_name3.code,
        }
        response = self.client.put(f'{self.url}{self.work_type1.id}/', data, format='json')
        work_type = response.json()
        data = {
            'id': self.work_type1.id, 
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 30, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id, 
            'work_type_name': {
                'id': self.work_type_name3.id,
                'code': self.work_type_name3.code,
                'name': self.work_type_name3.name,
            }
        }
        self.assertEqual(work_type, data)

    def test_update_by_id(self):
        data = {
            'max_workers_amount': 30,
            'work_type_name_id': self.work_type_name3.id,
        }
        response = self.client.put(f'{self.url}{self.work_type1.id}/', data, format='json')
        work_type = response.json()
        data = {
            'id': self.work_type1.id, 
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 30, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id, 
            'work_type_name': {
                'id': self.work_type_name3.id,
                'code': self.work_type_name3.code,
                'name': self.work_type_name3.name,
            }
        }
        self.assertEqual(work_type, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.work_type1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(WorkType.objects.get(id=self.work_type1.id).dttm_deleted)

    def test_get_efficiency(self):
        dt_now = datetime.now().date()
        tomorrow = dt_now + timedelta(days=1)
        after_tomorrow = dt_now + timedelta(days=2)
        after_after_tomorrow = dt_now + timedelta(days=3)

        main('2019.1.1', (datetime.now() + timedelta(days=365)).strftime('%Y.%m.%d'), region_id=1)
        op_name = OperationTypeName.objects.create(
            name='Test',
        )
        op_name3 = OperationTypeName.objects.create(
            name='Test3',
        )
        op_type = OperationType.objects.create(
            work_type=self.work_type1,
            operation_type_name=op_name,
        )
        op_type3 = OperationType.objects.create(
            work_type=self.work_type3,
            operation_type_name=op_name3,
        )

        for i in range(3):
            dt = dt_now + timedelta(days=i)
            for j in range(24):
                PeriodClients.objects.create(
                    value=2,
                    operation_type=op_type,
                    dttm_forecast=datetime.combine(dt, time(j)),
                )
                PeriodClients.objects.create(
                    value=1,
                    operation_type=op_type3,
                    dttm_forecast=datetime.combine(dt, time(j)),
                )

        wd = WorkerDay.objects.create(
            dttm_work_start=datetime.combine(dt_now, time(hour=9)),
            dttm_work_end=datetime.combine(dt_now, time(hour=18)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=dt_now,
            worker=self.user2,
            is_approved=True,
            is_fact=False,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd,
            work_type=self.work_type1,
        )
        WorkerDay.objects.create(
            type=WorkerDay.TYPE_SICK,
            dt=dt_now,
            worker=self.user2,
            is_approved=False,
            is_fact=False,
        )

        WorkerDay.objects.create(
            type=WorkerDay.TYPE_HOLIDAY,
            dt=tomorrow,
            worker=self.user2,
            is_approved=True,
            is_fact=False,
        )
        wd2 = WorkerDay.objects.create(
            dttm_work_start=datetime.combine(tomorrow, time(hour=10)),
            dttm_work_end=datetime.combine(tomorrow, time(hour=22)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=tomorrow,
            worker=self.user2,
            is_approved=False,
            is_fact=False,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd2,
            work_type=self.work_type1,
        )

        wd3 = WorkerDay.objects.create(
            dttm_work_start=datetime.combine(after_tomorrow, time(hour=10)),
            dttm_work_end=datetime.combine(after_tomorrow, time(hour=15)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=after_tomorrow,
            worker=self.user2,
            is_approved=True,
            is_fact=False,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd3,
            work_type=self.work_type1,
        )
        wd4 = WorkerDay.objects.create(
            dttm_work_start=datetime.combine(after_tomorrow, time(hour=10)),
            dttm_work_end=datetime.combine(after_tomorrow, time(hour=22)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=after_tomorrow,
            worker=self.user2,
            is_approved=False,
            is_fact=False,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd4,
            work_type=self.work_type3,
        )

        url = f'{self.url}efficiency/'

        get_params = {
            'shop_id': self.shop.id,
            'from_dt': Converter.convert_date(dt_now),
            'to_dt': Converter.convert_date(dt_now + timedelta(days=2)),
        }
        response = self.client.get(url, data=get_params)
        data = response.json()
        self.assertEqual(len(data['tt_periods']['real_cashiers']), 72)
        self.assertEqual(len(data['tt_periods']['predict_cashier_needs']), 72)
        self.assertEqual(data['tt_periods']['real_cashiers'][9]['amount'], 1.0)
        self.assertEqual(data['tt_periods']['real_cashiers'][34]['amount'], 0.0)
        day_stats = data['day_stats']
        self.assertEqual(day_stats['covering'][Converter.convert_date(dt_now)], 0.125)
        self.assertEqual(day_stats['predict_hours'][Converter.convert_date(dt_now)], 72.0)
        self.assertEqual(day_stats['graph_hours'][Converter.convert_date(dt_now)], 9.0)

        get_params['graph_type'] = 'plan_edit'
        response = self.client.get(url, data=get_params)
        data = response.json()
        self.assertEqual(len(data['tt_periods']['real_cashiers']), 72)
        self.assertEqual(len(data['tt_periods']['predict_cashier_needs']), 72)
        self.assertEqual(data['tt_periods']['real_cashiers'][9]['amount'], 0.0)
        self.assertEqual(data['tt_periods']['real_cashiers'][34]['amount'], 1.0)
        day_stats = data['day_stats']
        self.assertEqual(day_stats['covering'][Converter.convert_date(tomorrow)], 0.16666666666666666)
        self.assertEqual(day_stats['predict_hours'][Converter.convert_date(tomorrow)], 72.0)
        self.assertEqual(day_stats['graph_hours'][Converter.convert_date(tomorrow)], 12.0)

        get_params['work_type_ids'] = [self.work_type1.id]
        response = self.client.get(url, data=get_params)
        day_stats = response.json()['day_stats']
        self.assertEqual(day_stats['covering'][Converter.convert_date(after_tomorrow)], 0)
        self.assertEqual(day_stats['predict_hours'][Converter.convert_date(after_tomorrow)], 48.0)
        self.assertEqual(day_stats['graph_hours'][Converter.convert_date(after_tomorrow)], 0)

        get_params['work_type_ids'] = [self.work_type3.id]
        response = self.client.get(url, data=get_params)
        day_stats = response.json()['day_stats']
        self.assertEqual(day_stats['covering'][Converter.convert_date(after_tomorrow)], 0.5)
        self.assertEqual(day_stats['predict_hours'][Converter.convert_date(after_tomorrow)], 24.0)
        self.assertEqual(day_stats['graph_hours'][Converter.convert_date(after_tomorrow)], 12.0)

        wd5 = WorkerDay.objects.create(
            dttm_work_start=datetime.combine(after_after_tomorrow, time(hour=10)),
            dttm_work_end=datetime.combine(after_after_tomorrow, time(hour=22)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=after_after_tomorrow,
            worker=self.user2,
            is_approved=True,
            is_fact=False,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd5,
            work_type=self.work_type1,
        )
        for j in range(10, 18):
            PeriodClients.objects.create(
                value=1,
                operation_type=op_type,
                dttm_forecast=datetime.combine(after_after_tomorrow, time(j)),
            )

        del get_params['graph_type']
        del get_params['work_type_ids']
        get_params['indicators'] = 'true'
        get_params['efficiency'] = 'false'
        get_params['from_dt'] = Converter.convert_date(dt_now.replace(day=1))
        get_params['to_dt'] = Converter.convert_date(dt_now.replace(day=1) + relativedelta(months=1, days=-1))
        response = self.client.get(url, data=get_params)
        resp_data = response.json()
        self.assertIn('indicators', resp_data)
        self.assertNotIn('day_stats', resp_data)
        self.assertEqual(resp_data['indicators']['fot'], 880.0)
        self.assertEqual(resp_data['indicators']['covering'], 9.8)
        self.assertEqual(resp_data['indicators']['deadtime'], 15.4)
