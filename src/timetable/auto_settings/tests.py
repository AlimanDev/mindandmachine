import json
import uuid
from datetime import datetime, time, date, timedelta
from unittest.mock import patch

import pandas as pd
import requests
from django.test import override_settings
from django.utils.timezone import now
from rest_framework.test import APITestCase

from src.base.models import Break, WorkerPosition, Employment
from src.forecast.models import OperationType, OperationTypeName
from src.timetable.models import ShopMonthStat, WorkerDay, WorkerDayCashboxDetails, WorkType, WorkTypeName, \
    EmploymentWorkType
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestAutoSettings(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/auto_settings/set_timetable/'
        self.dt = now().date()

        create_departments_and_users(self, dt=date(2021, 1, 1))
        self.work_type_name = WorkTypeName.objects.create(name='Магазин')
        self.work_type_name2 = WorkTypeName.objects.create(name='Ломбард')
        self.operation_type_name = OperationTypeName.objects.create(name='Магазин', work_type_name=self.work_type_name)
        self.operation_type_name2 = OperationTypeName.objects.create(name='Ломбард', work_type_name=self.work_type_name2)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)
        self.work_type2 = WorkType.objects.create(
            work_type_name=self.work_type_name2,
            shop=self.shop)

        self.operation_type = OperationType.objects.create(
            work_type=self.work_type,
            operation_type_name=self.operation_type_name,
            shop=self.shop,
        )
        self.operation_type2 = OperationType.objects.create(
            work_type=self.work_type2,
            operation_type_name=self.operation_type_name2,
            shop=self.shop,
        )

        self.breaks = Break.objects.create(
            network=self.network,
            name='Перерывы для должности',
            value='[[0, 540, [30]]'
        )

        self.position = WorkerPosition.objects.create(
            name='Должность',
            network=self.network,
            breaks=self.breaks,
        )

        self.unused_position = WorkerPosition.objects.create(
            name='Не используемая должность',
            network=self.network,
            breaks=self.breaks,
        )

        self.client.force_authenticate(user=self.user1)

        self._create_empls_work_types()

    def test_set_timetable_new(self):

        timetable = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            status=ShopMonthStat.PROCESSING,
            dttm_status_change=now()
        )

        dt = now().date()
        tm_from = time(10, 0, 0)
        tm_to = time(20, 0, 0)

        dttm_from = Converter.convert_datetime(
            datetime.combine(dt, tm_from),
        )

        dttm_to = Converter.convert_datetime(
            datetime.combine(dt, tm_to),
        )
        self.assertEqual(len(WorkerDay.objects.all()), 0)
        self.assertEqual(len(WorkerDayCashboxDetails.objects.all()), 0)

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.user3.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'work_type_id': self.work_type2.id,
                                 'percent': 100,
                             }]
                             }
                        ]
                    },
                    self.user4.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'H',
                             }
                        ]
                    }
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        wd = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type=WorkerDay.TYPE_WORKDAY
        )
        self.assertEqual(len(wd), 1)

        self.assertEqual(WorkerDayCashboxDetails.objects.filter(
            worker_day=wd[0],
            work_type=self.work_type2,
        ).count(), 1)

        self.assertEqual(WorkerDay.objects.filter(
            worker=self.user4,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            shop__isnull=True,
            dttm_work_start__isnull=True,
            dttm_work_end__isnull=True
        ).count(), 1)

    def test_set_timetable_change_existed(self):
        timetable = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            status=ShopMonthStat.PROCESSING,
            dttm_status_change=now()
        )

        dt = now().date()
        tm_from = time(10, 0, 0)
        tm_to = time(20, 0, 0)

        dttm_from = Converter.convert_datetime(
            datetime.combine(dt, tm_from),
        )

        dttm_to = Converter.convert_datetime(
            datetime.combine(dt, tm_to),
        )


        self.wd1_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
        )
        self.wd1_plan_not_approved = WorkerDay.objects.create(
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_HOLIDAY,
            parent_worker_day=self.wd1_plan_approved
        )

        self.wd2_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user3,
            employment=self.employment3,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
        )

        self.wd3_plan_not_approved = WorkerDay.objects.create(
            worker=self.user4,
            employment=self.employment4,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_HOLIDAY,
        )

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.user2.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'work_type_id': self.work_type2.id,
                                 'percent': 100,
                             }]
                             }
                        ]
                    },
                    self.user3.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'work_type_id': self.work_type2.id,
                                 'percent': 100,
                             }]
                             }
                        ]
                    },
                    self.user4.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'H',
                             }
                        ]
                    }
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        self.assertTrue(WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
            id=self.wd1_plan_approved.id
        ).exists())

        wd1 = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type=WorkerDay.TYPE_WORKDAY,
            id=self.wd1_plan_not_approved.id,
            is_approved = False
        )
        self.assertEqual(len(wd1), 1)

        wd2 = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type=WorkerDay.TYPE_WORKDAY,
            parent_worker_day_id=self.wd2_plan_approved.id,
            is_approved=False
        )
        self.assertEqual(len(wd2), 1)

        self.assertEqual(WorkerDay.objects.filter(
            worker=self.user4,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            dttm_work_start__isnull=True,
            dttm_work_end__isnull=True,
            shop_id__isnull=True,
            parent_worker_day__isnull=True,
            is_approved=False
        ).count(), 1)

        self.assertEqual(WorkerDayCashboxDetails.objects.filter(
            worker_day__in=[wd1[0], wd2[0]],
            work_type=self.work_type2,
        ).count(), 2)


    def test_delete_tt_created_by(self):
        dt_from = date.today() + timedelta(days=1)
        for day in range(3):
            dt_from = dt_from + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment1,
                worker=self.employment1.user,
                shop=self.employment1.shop,
                dt=dt_from,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
                created_by=self.user1,
            )

        for day in range(4):
            dt_from = dt_from + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment1,
                worker=self.employment1.user,
                shop=self.employment1.shop,
                dt=dt_from,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt_from, time(9)),
                dttm_work_end=datetime.combine(dt_from, time(22)),
                is_approved=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        self.assertEqual(WorkerDay.objects.count(), 7)
        response = self.client.post('/rest_api/auto_settings/delete_timetable/', data={'dt_from': date.today() + timedelta(days=2), 'dt_to':dt_from, 'shop_id': self.employment1.shop_id, 'delete_created_by': True})
        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.count(), 0)

    def test_delete_tt(self):
        dt_from = date.today() + timedelta(days=1)
        for day in range(3):
            dt_from = dt_from + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment1,
                worker=self.employment1.user,
                shop=self.employment1.shop,
                dt=dt_from,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
                created_by=self.user1,
            )

        for day in range(4):
            dt_from = dt_from + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment1,
                worker=self.employment1.user,
                shop=self.employment1.shop,
                dt=dt_from,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt_from, time(9)),
                dttm_work_end=datetime.combine(dt_from, time(22)),
                is_approved=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        self.assertEqual(WorkerDay.objects.count(), 7)
        response = self.client.post('/rest_api/auto_settings/delete_timetable/', data={'dt_from': date.today() + timedelta(days=2), 'dt_to':dt_from, 'shop_id': self.employment1.shop_id})
        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.count(), 3)

    def test_bad_dates(self):
        response = self.client.post(
            path='/rest_api/auto_settings/create_timetable/',
            data={'shop_id': self.shop.id, 'dt_from': '2020-10-31', 'dt_to': '2020-10-01'},
        )
        self.assertEqual(response.json(), ['Дата начала должна быть меньше чем дата окончания.'])

    def test_no_settings(self):
        self.shop.settings = None
        self.shop.save()
        response = self.client.post(
            path='/rest_api/auto_settings/create_timetable/',
            data={
                'shop_id': self.shop.id,
                'dt_from': datetime.now().date() + timedelta(days=2),
                'dt_to': datetime.now().date() + timedelta(days=5),
            },
        )
        self.assertEqual(response.json(), ['Необходимо выбрать шаблон смен.'])

    def _create_empls_work_types(self):
        EmploymentWorkType.objects.create(employment=self.employment2, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment3, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment4, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment6, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment7, work_type=self.work_type)

    def _test_create_tt(self, dt_from, dt_to, use_not_approved=True):
        ShopMonthStat.objects.filter(shop=self.employment2.shop).update(status=ShopMonthStat.NOT_DONE)
        # так переопределяем, чтобы можно было константные значения дат из прошлого использовать
        with self.settings(REBUILD_TIMETABLE_MIN_DELTA=-9999):
            class res:
                def json(self):
                    return {'task_id': 1}

            with patch.object(requests, 'post', return_value=res()) as mock_post:
                response = self.client.post(
                    '/rest_api/auto_settings/create_timetable/',
                    {
                        'shop_id': self.shop.id,
                        'dt_from': dt_from,
                        'dt_to': dt_to,
                        'use_not_approved': use_not_approved,
                    }
                )
                print(response.status_code)
                print(response.content.decode())
                data = json.loads(mock_post.call_args[1]['data'])
                self.assertEqual(response.status_code, 200)

            return data

    def test_create_tt(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)

        dt = dt_from
        for day in range(4):
            dt = dt + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(9)),
                dttm_work_end=datetime.combine(dt, time(22)),
                is_approved=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
            )
        Employment.objects.filter(id=self.employment6.id).update(position_id=self.position.id)

        wd = WorkerDay.objects.create(
            employment=self.employment3,
            worker=self.employment3.user,
            shop=self.employment3.shop,
            dt=dt_to,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_to, time(9)),
            dttm_work_end=datetime.combine(dt_to, time(22)),
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd
        )

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(len(data['work_types']), 2)
        self.assertEqual(len(data['cashiers']), 5)
        self.assertEqual(len(employment2Info['workdays']), 4)
        self.assertEqual(employment2Info['workdays'][0]['dt'], (dt_from + timedelta(1)).strftime('%Y-%m-%d'))
        self.assertEqual(employment3Info['workdays'][-1]['dt'], dt_to.strftime('%Y-%m-%d'))
        self.assertEqual(len(data['algo_params']['breaks_triplets']), 2)
        self.assertIsNotNone(data['algo_params']['breaks_triplets'].get(str(self.position.id)))
        self.assertIsNone(data['algo_params']['breaks_triplets'].get(str(self.unused_position.id)))

    def test_create_tt_full_month(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 151.0)
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

    def test_create_tt_first_part_of_month(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 14)

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)  # в прошлом вариант 40, что странно
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)  # в прошлом вариант 40, что странно

    def test_create_tt_second_part_of_month(self):
        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    def test_create_tt_full_month_with_vacations_not_approved(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(round(employment2Info['norm_work_amount'], 5), round(134.82142857142856, 5))
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

    def test_create_tt_full_month_with_vacations_approved(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        # проверка, что для use_not_approved=False не учитывается неподтв. график
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 151.0)
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_VACATION,
                is_approved=True,
            )
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(round(employment2Info['norm_work_amount'], 5), round(134.82142857142856, 5))
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

    def test_create_tt_second_part_of_month_with_vacations_in_first_part_or_month(self):
        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        dt = date(2021, 2, 1)
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_VACATION,
                is_approved=True,
            )
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)  # в прошлом варианте 81.85587, почему получалось больше?
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    def test_create_tt_second_part_of_month_with_vacations_in_second_part_or_month(self):
        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_VACATION,
                is_approved=True,
            )
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 59.32142857142857)  # в прошлом варианте 67.41071428571429, какой вариант правильнее?
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    def test_create_tt_sum_for_first_and_second_parts_of_month_equal_to_full_month_norm(self):
        dt = date(2021, 2, 15)
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_VACATION,
            )

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 14)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        first_month_part_norm_work_amount = employment2Info['norm_work_amount']
        self.assertEqual(first_month_part_norm_work_amount, 75.5)

        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        seconds_month_part_norm_work_amount = employment2Info['norm_work_amount']
        self.assertEqual(seconds_month_part_norm_work_amount, 59.32142857142857)

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        full_month_norm_work_amount = employment2Info['norm_work_amount']
        self.assertEqual(full_month_norm_work_amount, 134.82142857142856)

        self.assertEqual(
            first_month_part_norm_work_amount + seconds_month_part_norm_work_amount, full_month_norm_work_amount)

    def test_create_tt_second_part_of_month_with_holidays_in_fist_part(self):
        for dt in pd.date_range(date(2021, 2, 1), date(2021, 2, 14)):
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_HOLIDAY,
            )

        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)  # старый вариант 151.0 (новый вариант не учитывает неотработанные часы) # TODO: надо сделать так, чтобы учитывал
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)  # старый вариант 75.5 (сколько должно быть? как должно учитываться отсутствие данных?)

    def test_create_tt_second_part_of_month_with_work_days_in_fist_part(self):
        for dt in pd.date_range(date(2021, 2, 1), date(2021, 2, 14)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(9)),
                dttm_work_end=datetime.combine(dt, time(22)),
                is_approved=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id, data['cashiers']))[0]
        # TODO: сделать учет часов, отработанных за пред. период (откуда брать часы или плана или из факта?)
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)  # старый вариант -13 -- это правильно?
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    def test_create_tt_full_month_for_employment_hired_in_middle_of_the_month(self):
        Employment.objects.filter(id=self.employment2.id).update(dt_hired=date(2021, 2, 13))
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 71.0)  # старый вариант -- 151.0 (не учитывает дату взятия на работу?)

    def test_create_tt_full_month_for_employment_fired_in_middle_of_the_month(self):
        Employment.objects.filter(id=self.employment2.id).update(dt_fired=date(2021, 2, 17))
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 104.0)  # старый вариант -- 151.0 (не учитывает дату увольнения?)

    def test_create_tt_full_month_for_multiple_employments_in_the_same_shop(self):
        empl2_2 = Employment.objects.create(  # второе трудоустройство на пол ставки с другой должностью
            network=self.network,
            code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            user=self.user2,
            shop=self.shop,
            function_group=self.employee_group,
            norm_work_hours=50,
        )
        Employment.objects.filter(id=empl2_2.id).update(position_id=self.position.id)
        EmploymentWorkType.objects.create(
            employment=empl2_2,
            work_type=self.work_type,
        )

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)

        # не 151.0 + 75.5 т.к. час в сокращенном дне вычитается полностью, а не как доля от ставки
        self.assertEqual(
            sum(i['norm_work_amount'] for i in
                filter(lambda x: x['general_info']['id'] == self.user2.id, data['cashiers'])), 151.0 + 75.0)
