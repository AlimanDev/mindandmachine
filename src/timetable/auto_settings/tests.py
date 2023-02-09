import json
from unittest import mock
import uuid
from datetime import datetime, time, date, timedelta
from unittest import skip, expectedFailure
from unittest.mock import patch

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.test import override_settings
from django.core.cache import cache
from django.utils.timezone import now
from rest_framework.test import APITestCase

from src.base.models import Break, WorkerPosition, Employment
from src.timetable.models import ShopMonthStat, WorkerDay, WorkerDayCashboxDetails, WorkType, WorkTypeName, \
    EmploymentWorkType, WorkerDayType
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter
from src.util.mock import MockResponse

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestAutoSettings(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/auto_settings/set_timetable/'
        cls.dt = now().date()

        cls.create_departments_and_users(dt=date(2021, 1, 1))
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type_name2 = WorkTypeName.objects.create(name='Ломбард', network=cls.network)
        cls.operation_type_name = cls.work_type_name.operation_type_name
        cls.operation_type_name2 = cls.work_type_name2.operation_type_name
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(
            work_type_name=cls.work_type_name2,
            shop=cls.shop)

        cls.operation_type = cls.work_type.operation_type
        cls.operation_type2 = cls.work_type2.operation_type

        cls.breaks = Break.objects.create(
            network=cls.network,
            name='Перерывы для должности',
            value='[[0, 540, [30]]]'
        )

        cls.position = WorkerPosition.objects.create(
            name='Должность',
            network=cls.network,
            breaks=cls.breaks,
        )

        cls.unused_position = WorkerPosition.objects.create(
            name='Не используемая должность',
            network=cls.network,
            breaks=cls.breaks,
        )
        cls._create_empls_work_types()

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(user=self.user1)

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
                    self.employee3.id: {
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
                    self.employee4.id: {
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
            employee=self.employee3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type_id=WorkerDay.TYPE_WORKDAY,
            source=WorkerDay.SOURCE_ALGO,
        )
        self.assertEqual(len(wd), 1)

        self.assertEqual(WorkerDayCashboxDetails.objects.filter(
            worker_day=wd[0],
            work_type=self.work_type2,
        ).count(), 1)

        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee4,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            shop__isnull=True,
            dttm_work_start__isnull=True,
            dttm_work_end__isnull=True,
            source=WorkerDay.SOURCE_ALGO,
        ).count(), 1)

    @expectedFailure
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
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
        )
        self.wd1_plan_not_approved = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_HOLIDAY,
            parent_worker_day=self.wd1_plan_approved
        )

        self.wd2_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee3,
            employment=self.employment3,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
        )

        self.wd3_plan_not_approved = WorkerDay.objects.create(
            employee=self.employee4,
            employment=self.employment4,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_HOLIDAY,
        )

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.employee2.id: {
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
                    self.employee3.id: {
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
                    self.employee4.id: {
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
            employee=self.employee2,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
            id=self.wd1_plan_approved.id
        ).exists())

        wd1 = WorkerDay.objects.filter(
            shop=self.shop,
            employee=self.employee2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type_id=WorkerDay.TYPE_WORKDAY,
            id=self.wd1_plan_not_approved.id,
            is_approved=False,
            source=WorkerDay.SOURCE_ALGO,
        )
        self.assertEqual(len(wd1), 1)

        wd2 = WorkerDay.objects.filter(
            shop=self.shop,
            employee=self.employee3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type_id=WorkerDay.TYPE_WORKDAY,
            # TODO: что за случай? -- почему подтвежденная версия становится черновиком?
            parent_worker_day_id=self.wd2_plan_approved.id,
            is_approved=False
        )
        self.assertEqual(len(wd2), 1)

        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee4,
            type_id=WorkerDay.TYPE_HOLIDAY,
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
                employee=self.employment1.employee,
                shop=self.employment1.shop,
                dt=dt_from,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
                created_by=self.user1,
            )

        for day in range(4):
            dt_from = dt_from + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment1,
                employee=self.employment1.employee,
                shop=self.employment1.shop,
                dt=dt_from,
                type_id=WorkerDay.TYPE_WORKDAY,
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
                employee=self.employment1.employee,
                shop=self.employment1.shop,
                dt=dt_from,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
                created_by=self.user1,
            )

        for day in range(4):
            dt_from = dt_from + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment1,
                employee=self.employment1.employee,
                shop=self.employment1.shop,
                dt=dt_from,
                type_id=WorkerDay.TYPE_WORKDAY,
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
        dt_next_month = date.today() + relativedelta(day=31)
        response = self.client.post(
            path='/rest_api/auto_settings/create_timetable/',
            data={
                'shop_id': self.shop.id,
                'dt_from': dt_next_month + timedelta(days=2),
                'dt_to': dt_next_month + timedelta(days=5),
            },
        )
        self.assertEqual(response.json(), ['Необходимо выбрать шаблон смен.'])

    @classmethod
    def _create_empls_work_types(cls):
        EmploymentWorkType.objects.create(employment=cls.employment2, work_type=cls.work_type)
        EmploymentWorkType.objects.create(employment=cls.employment3, work_type=cls.work_type)
        EmploymentWorkType.objects.create(employment=cls.employment4, work_type=cls.work_type)
        EmploymentWorkType.objects.create(employment=cls.employment6, work_type=cls.work_type)
        EmploymentWorkType.objects.create(employment=cls.employment7, work_type=cls.work_type)
        EmploymentWorkType.objects.create(employment=cls.employment8_old, work_type=cls.work_type)
        EmploymentWorkType.objects.create(employment=cls.employment8, work_type=cls.work_type)

    def _test_create_tt(self, dt_from, dt_to, use_not_approved=True, shop_id=None):
        ShopMonthStat.objects.filter(shop_id=shop_id or self.employment2.shop_id).update(status=ShopMonthStat.NOT_DONE)
        # так переопределяем, чтобы можно было константные значения дат из прошлого использовать
        self.network.rebuild_timetable_min_delta = -9999
        self.network.save()

        with patch.object(requests, 'post', return_value=MockResponse(json_data={'task_id': 1}, status_code=200)) as mock_post:
            response = self.client.post(
                '/rest_api/auto_settings/create_timetable/',
                {
                    'shop_id': shop_id or self.shop.id,
                    'dt_from': dt_from,
                    'dt_to': dt_to,
                    'use_not_approved': use_not_approved,
                }
            )
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
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
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
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
            )
        Employment.objects.filter(id=self.employment6.id).update(position_id=self.position.id)

        wd = WorkerDay.objects.create(
            employment=self.employment3,
            employee_id=self.employment3.employee_id,
            shop=self.employment3.shop,
            dt=dt_to,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_to, time(9)),
            dttm_work_end=datetime.combine(dt_to, time(22)),
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd
        )

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(len(data['work_types']), 2)
        self.assertEqual(len(data['cashiers']), 5)
        self.assertEqual(len(employment2Info['workdays']), 4)
        self.assertEqual(employment2Info['workdays'][0]['dt'], (dt_from + timedelta(1)).strftime('%Y-%m-%d'))
        self.assertEqual(employment3Info['workdays'][-1]['dt'], dt_to.strftime('%Y-%m-%d'))
        self.assertEqual(len(data['algo_params']['breaks_triplets']), 2)
        self.assertIsNotNone(data['algo_params']['breaks_triplets'].get(str(self.position.id)))
        self.assertIsNone(data['algo_params']['breaks_triplets'].get(str(self.unused_position.id)))

    def test_create_tt_wd_in_other_shops(self):
        dt_from = (date.today() + timedelta(days=31)).replace(day=1) + timedelta(days=1)
        dt_from_tt = dt_from + timedelta(days=1)
        dt_to = dt_from + relativedelta(day=31)

        for day in range(2):
            dt_from = dt_from + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop if day % 2 == 0 else self.shop2,
                dt=dt_from,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt_from, time(9)),
                dttm_work_end=datetime.combine(dt_from, time(22)),
                is_approved=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        for day in range(3):
            dt_from = dt_from + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt_from,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
            )
        self.employment6.position = self.position
        self.employment6.save()
        EmploymentWorkType.objects.create(employment=self.employment6, work_type=self.work_type)
        wd = WorkerDay.objects.create(
            employment=self.employment3,
            employee_id=self.employment3.employee_id,
            shop=self.employment3.shop,
            dt=dt_to,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_from, time(9)),
            dttm_work_end=datetime.combine(dt_from, time(22)),
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd
        )
        data = self._test_create_tt(dt_from_tt, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id,data['cashiers']))[0]
        self.assertEqual(len(employment2Info['workdays']), 2)
        self.assertEqual(employment2Info['workdays'][0]['dt'], dt_from_tt.strftime('%Y-%m-%d'))
        self.assertEqual(employment2Info['workdays'][1]['type'], 'R')

    def test_set_timetable_not_replace_wds_in_other_shops(self):
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

        self.wd1 = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
        )
        self.wd2 = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt + timedelta(1),
            is_fact=False,
            type_id=WorkerDay.TYPE_HOLIDAY,
        )

        self.wd3 = WorkerDay.objects.create(
            shop=self.shop2,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt + timedelta(2),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
        )

        self.wd4 = WorkerDay.objects.create(
            shop=self.shop2,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt + timedelta(3),
            type_id=WorkerDay.TYPE_EMPTY,
        )

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.employee2.id: {
                        'workdays': [
                            {
                                'dt': Converter.convert_date(dt),
                                'type': 'W',
                                'dttm_work_start': dttm_from,
                                'dttm_work_end': dttm_to,
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                            {
                                'dt': Converter.convert_date(dt + timedelta(1)),
                                'type': 'H',
                                'dttm_work_start': None,
                                'dttm_work_end': None,
                                'details': [],
                            },
                            {
                                'dt': Converter.convert_date(dt + timedelta(2)),
                                'type': 'W',
                                'dttm_work_start': dttm_from,
                                'dttm_work_end': dttm_to,
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                            {
                                'dt': Converter.convert_date(dt + timedelta(3)),
                                'type': 'W',
                                'dttm_work_start': dttm_from,
                                'dttm_work_end': dttm_to,
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                        ]
                    },
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.filter(
            shop=self.shop,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
        ).count(), 2)

        self.assertEqual(WorkerDay.objects.filter(
            shop=self.shop2,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
        ).first().dt, self.dt + timedelta(2))

    @skip("not working correctly since 2023")
    def test_create_tt_full_month(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 151.0)
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

    @skip("not working correctly since 2023")
    def test_create_tt_first_part_of_month(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 14)

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)  # в прошлом вариант 40, что странно
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)  # в прошлом вариант 40, что странно

    @skip("not working correctly since 2023")
    def test_create_tt_second_part_of_month(self):
        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_full_month_with_vacations_not_approved(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(round(employment2Info['norm_work_amount'], 5), round(134.82142857142856, 5))
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

    @skip("not working correctly since 2023")
    def test_create_tt_full_month_with_vacations_approved(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        # проверка, что для use_not_approved=False не учитывается неподтв. график
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 151.0)
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            for day in range(3):
                dt = dt + timedelta(days=1)
                WorkerDay.objects.create(
                    employment=self.employment2,
                    employee=self.employment2.employee,
                    shop=self.employment2.shop,
                    dt=dt,
                    type_id=WorkerDay.TYPE_VACATION,
                    is_approved=True,
                )
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(round(employment2Info['norm_work_amount'], 5), round(134.82142857142856, 5))
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)

    @skip("not working correctly since 2023")
    def test_create_tt_second_part_of_month_with_vacations_in_first_part_or_month(self):
        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        for dt in pd.date_range(date(2021, 2, 1), date(2021, 2, 3)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=True,
            )
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_second_part_of_month_with_vacations_in_second_part_or_month(self):
        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=True,
            )
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 59.32142857142857)
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_sum_for_first_and_second_parts_of_month_equal_to_full_month_norm(self):
        for dt in pd.date_range(date(2021, 2, 15), date(2021, 2, 18)):
            dt = dt + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
            )

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 14)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        first_month_part_norm_work_amount = employment2Info['norm_work_amount']
      #  self.assertEqual(first_month_part_norm_work_amount, 75.5)

        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        seconds_month_part_norm_work_amount = employment2Info['norm_work_amount']
        self.assertEqual(seconds_month_part_norm_work_amount, 53.92857142857143)

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        full_month_norm_work_amount = employment2Info['norm_work_amount']
        self.assertEqual(full_month_norm_work_amount, 129.42857142857142)

        self.assertEqual(
            round(first_month_part_norm_work_amount + seconds_month_part_norm_work_amount, 5), round(full_month_norm_work_amount, 5))

    @skip("not working correctly since 2023")
    def test_create_tt_second_part_of_month_with_holidays_in_fist_part(self):
        for dt in pd.date_range(date(2021, 2, 1), date(2021, 2, 14)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
            )

        dt_from = date(2021, 2, 15)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)  # TODO: в это случае должно быть 150?
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_second_part_of_month_with_work_days_in_fist_part(self):
        for dt in pd.date_range(date(2021, 2, 1), date(2021, 2, 14)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
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
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], -13.5)  # TODO: минусовая норма это ок?
        self.assertEqual(employment3Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_full_month_for_employment_hired_in_middle_of_the_month(self):
        Employment.objects.filter(id=self.employment2.id).update(dt_hired=date(2021, 2, 13))
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 71.0)  # старый вариант -- 151.0 (не учитывает дату взятия на работу?)

    @skip("not working correctly since 2023")
    def test_create_tt_full_month_for_employment_fired_in_middle_of_the_month(self):
        Employment.objects.filter(id=self.employment2.id).update(dt_fired=date(2021, 2, 17))
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 104.0)  # старый вариант -- 151.0 (не учитывает дату увольнения?)

    @skip("not working correctly since 2023")
    def test_create_tt_full_month_for_multiple_employments_in_the_same_shop(self):
        empl2_2 = Employment.objects.create(  # второе трудоустройство на пол ставки с другой должностью
            code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            employee=self.employee2,
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

        # 75.0, а не 75.5 т.к. час в сокращенном дне вычитается полностью, а не как доля от ставки
        self.assertEqual(
            sum(i['norm_work_amount'] for i in
                filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers'])), 151.0 + 75.0)

    @skip("not working correctly since 2023")
    def test_create_tt_full_month_with_acc_period_3_months_and_fact_work_hours_in_prev_month(self):
        self.network.accounting_period_length = 3
        self.network.consider_remaining_hours_in_prev_months_when_calc_norm_hours = True
        self.network.save()

        for dt in pd.date_range(date(2021, 1, 1), date(2021, 1, 15)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 137.14678899082568)

    @skip("not working correctly since 2023")
    def test_create_tt_first_part_of_month_with_vacations_work_days_and_holidays_in_second_part(self):
        self.network.accounting_period_length = 3
        self.network.save()

        for dt in pd.date_range(date(2021, 1, 1), date(2021, 1, 12)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in pd.date_range(date(2021, 2, 15), date(2021, 2, 21)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=True,
                is_fact=False,
            )

        for dt in pd.date_range(date(2021, 1, 22), date(2021, 1, 26)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in pd.date_range(date(2021, 1, 27), date(2021, 1, 28)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
                is_fact=False,
            )

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 14)
        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_first_part_of_month_with_vacations_work_days_and_no_data_in_second_part(self):
        self.network.accounting_period_length = 3
        self.network.save()

        for dt in pd.date_range(date(2021, 1, 1), date(2021, 1, 12)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in pd.date_range(date(2021, 2, 15), date(2021, 2, 21)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=True,
                is_fact=False,
            )

        for dt in pd.date_range(date(2021, 1, 22), date(2021, 1, 26)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in pd.date_range(date(2021, 1, 27), date(2021, 1, 28)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
                is_fact=False,
            )

        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 14)
        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 75.5)

    @skip("not working correctly since 2023")
    def test_create_tt_start_in_one_month_end_in_the_other(self):
        self.network.accounting_period_length = 6
        self.network.save()

        for dt in pd.date_range(date(2021, 1, 1), date(2021, 1, 12)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in pd.date_range(date(2021, 2, 1), date(2021, 2, 14)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        wd = WorkerDay.objects.create(
            employment=self.employment2,
            employee=self.employment2.employee,
            shop=self.employment2.shop,
            dt=date(2021, 2, 15),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(date(2021, 2, 15), time(10)),
            dttm_work_end=datetime.combine(date(2021, 2, 15), time(22, 15)),
            is_approved=True,
            is_fact=True,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
        )

        for dt in pd.date_range(date(2021, 3, 1), date(2021, 3, 7)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21, 15)),
                is_approved=True,
                is_fact=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        wd = WorkerDay.objects.create(
            employment=self.employment2,
            employee=self.employment2.employee,
            shop=self.employment2.shop,
            dt=date(2021, 3, 8),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(date(2021, 3, 8), time(10)),
            dttm_work_end=datetime.combine(date(2021, 3, 8), time(23, 15)),
            is_approved=True,
            is_fact=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
        )

        for dt in pd.date_range(date(2021, 3, 9), date(2021, 3, 16)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
                is_fact=False,
            )

        dt_from = date(2021, 3, 25)
        dt_to = date(2021, 4, 5)
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        # TODO: правильный результат?
        self.assertEqual(employment2Info['norm_work_amount'], 73.03333333333333)  # {3: 43.86666666666666, 4: 29.166666666666664}

    @skip("not working correctly since 2023")
    def test_create_tt_part_of_month_with_workdays_and_vacation_in_prev_month_part(self):
        for dt in (date(2021, 3, 2), date(2021, 3, 4)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(19)),
                is_approved=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in (date(2021, 3, 1), date(2021, 3, 5)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
            )

        WorkerDay.objects.create(
            employment=self.employment2,
            employee=self.employment2.employee,
            shop=self.employment2.shop,
            dt=date(2021, 3, 3),
            type_id=WorkerDay.TYPE_VACATION,
            is_approved=True,
        )

        dt_from = date(2021, 3, 6)
        dt_to = date(2021, 3, 31)
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=False)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 154.3225806451613)

    @skip("not working correctly since 2023")
    def test_create_tt_in_the_middle_of_the_month_with_workdays_and_vacation_in_both_sides(self):
        for dt in (date(2021, 3, 2), date(2021, 3, 4)):
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(19)),
                is_approved=False,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        wd = WorkerDay.objects.create(
            employment=self.employment2,
            employee=self.employment2.employee,
            shop=self.employment2.shop,
            dt=date(2021, 3, 14),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(21, 15)),
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
        )

        wd = WorkerDay.objects.create(
            employment=self.employment2,
            employee=self.employment2.employee,
            shop=self.employment2.shop,
            dt=date(2021, 3, 24),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(17)),
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
        )

        for dt in (date(2021, 3, 1), date(2021, 3, 5)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
            )

        for dt in (date(2021, 3, 3), date(2021, 3, 15), date(2021, 3, 25)):
            WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        dt_from = date(2021, 3, 10)
        dt_to = date(2021, 3, 20)
        data = self._test_create_tt(dt_from, dt_to, use_not_approved=True)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 59.70161290322581)

    def test_create_tt_error_for_months_from_different_acc_periods(self):
        dt_from = date(2021, 3, 25)
        dt_to = date(2021, 4, 5)

        with patch.object(requests, 'post', return_value=MockResponse(json_data={'task_id': 1}, status_code=200)):
            response = self.client.post(
                '/rest_api/auto_settings/create_timetable/',
                {
                    'shop_id': self.shop.id,
                    'dt_from': dt_from,
                    'dt_to': dt_to,
                }
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), [
                'Небходимо выбрать интервал в рамках одного учетного периода.'
            ]
        )

    @skip('Иногда падает, надо поправить')
    def test_create_tt_division_by_zero_not_raised_with_2_empls(self):
        Employment.objects.filter(id=self.employment8_old.id).update(dt_hired='2020-01-10', dt_fired='2021-03-04')
        Employment.objects.filter(id=self.employment8.id).update(dt_hired='2021-03-05', dt_fired='3999-12-31')

        for dt in pd.date_range(date(2021, 3, 1), date(2021, 3, 4)):
            wd = WorkerDay.objects.create(
                employment=self.employment8_old,
                employee_id=self.employment8_old.employee_id,
                shop=self.employment8_old.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(19)),
                is_approved=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in (date(2021, 3, 5), date(2021, 3, 17)):
            wd = WorkerDay.objects.create(
                employment=self.employment8,
                employee=self.employment8.employee,
                shop=self.employment8.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(19)),
                is_approved=True,
            )
            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd,
            )

        for dt in (date(2021, 3, 18), date(2021, 3, 31)):
            WorkerDay.objects.create(
                employment=self.employment8,
                employee_id=self.employment8.employee_id,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
            )

        dt_from = date(2021, 3, 1)
        dt_to = date(2021, 3, 7)
        data = self._test_create_tt(dt_from, dt_to, shop_id=self.employment8.shop_id)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employment8_old.employee_id, data['cashiers']))[0]
        self.assertEqual(employment2Info['norm_work_amount'], 32.0)  # TODO-devx: не уверен, что верное значение, надо будет проверить

    def test_create_timetable_with_fired(self):
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)

        dt = dt_from
        for day in range(4):
            dt = dt + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
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
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
            )
        self.employment2.dt_fired = date(2021, 2, 3)
        self.employment2.save()

        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        self.assertEqual(len(employment2Info['workdays']), 27)  # почему 1 число не попадало?
        self.assertEqual(employment2Info['workdays'][1]['type'], 'W')
        self.assertEqual(employment2Info['workdays'][1]['dt'], '2021-02-03')
        self.assertEqual(employment2Info['workdays'][2]['type'], 'H')
        self.assertEqual(employment2Info['workdays'][2]['dt'], '2021-02-04')

    def test_set_timetable_with_wds_from_other_shops(self):
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

        self.wd1 = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
        )

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.employee2.id: {
                        'workdays': [
                            {
                                'dt': Converter.convert_date(dt),
                                'type': 'R',
                                'dttm_work_start': None,
                                'dttm_work_end': None,
                                'details': []
                            },
                        ]
                    },
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.filter(
            type="R",
        ).count(), 0)

        wd = WorkerDay.objects.filter(
            shop=self.shop,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
        ).first()

        self.assertEqual(wd.employee_id, self.employee2.id)
        self.assertEqual(wd.shop_id, self.shop.id)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)

    def test_set_timetable_with_is_work_hours_true_vacation(self):
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()

        timetable = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            status=ShopMonthStat.PROCESSING,
            dttm_status_change=now()
        )

        WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            type_id=WorkerDay.TYPE_VACATION,
            is_fact=False,
            is_approved=False,
        )

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.employee2.id: {
                        'workdays': [
                            {
                                'dt': Converter.convert_date(self.dt),
                                'type': WorkerDay.TYPE_VACATION,
                                'dttm_work_start': None,
                                'dttm_work_end': None,
                                'details': []
                            },
                        ]
                    },
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        vacation = WorkerDay.objects.filter(
            is_fact=False,
            type_id=WorkerDay.TYPE_VACATION,
            is_approved=False,
        ).first()
        self.assertTrue(vacation.work_hours > timedelta(0))

    def test_multiple_workerday_on_one_date_sent_to_algo(self):
        dt = date(2021, 2, 1)
        WorkerDayFactory(
            employment=self.employment8,
            employee=self.employment8.employee,
            shop=self.employment8.shop,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(15)),
            is_approved=True,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            employment=self.employment8,
            employee=self.employment8.employee,
            shop=self.employment8.shop,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(17)),
            dttm_work_end=datetime.combine(dt, time(23)),
            is_approved=True,
            cashbox_details__work_type=self.work_type,
        )

        data = self._test_create_tt(dt, dt, use_not_approved=True, shop_id=self.employment8.shop_id)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee8.id, data['cashiers']))[0]
        self.assertEqual(len(employment2Info['workdays']), 0)

        data = self._test_create_tt(dt, dt, use_not_approved=False, shop_id=self.employment8.shop_id)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee8.id, data['cashiers']))[0]
        self.assertEqual(len(employment2Info['workdays']), 2)
        self.assertEqual(employment2Info['workdays'][0]['type'], 'W')
        self.assertEqual(employment2Info['workdays'][0]['dt'], '2021-02-01')
        self.assertEqual(employment2Info['workdays'][1]['type'], 'W')
        self.assertEqual(employment2Info['workdays'][1]['dt'], '2021-02-01')

    def test_multiple_workerday_on_one_date_with_dt_fired_in_employment(self):
        dt = date(2021, 2, 1)
        Employment.objects.filter(id=self.employment8.id).update(dt_fired=date(3999, 12, 31))
        WorkerDayFactory(
            employment=self.employment8,
            employee=self.employment8.employee,
            shop=self.employment8.shop,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(15)),
            is_approved=True,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            employment=self.employment8,
            employee=self.employment8.employee,
            shop=self.employment8.shop,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(17)),
            dttm_work_end=datetime.combine(dt, time(23)),
            is_approved=True,
            cashbox_details__work_type=self.work_type,
        )

        data = self._test_create_tt(dt, dt, use_not_approved=True, shop_id=self.employment8.shop_id)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee8.id, data['cashiers']))[0]
        self.assertEqual(len(employment2Info['workdays']), 0)

        data = self._test_create_tt(dt, dt, use_not_approved=False, shop_id=self.employment8.shop_id)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee8.id, data['cashiers']))[0]
        self.assertEqual(len(employment2Info['workdays']), 2)
        self.assertEqual(employment2Info['workdays'][0]['type'], 'W')
        self.assertEqual(employment2Info['workdays'][0]['dt'], '2021-02-01')
        self.assertEqual(employment2Info['workdays'][1]['type'], 'W')
        self.assertEqual(employment2Info['workdays'][1]['dt'], '2021-02-01')

    def test_multiple_workerday_received_from_algo(self):
        timetable = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            status=ShopMonthStat.PROCESSING,
            dttm_status_change=now(),
        )

        dt = now().date()
        tm_from1 = time(10, 0, 0)
        tm_to1 = time(14, 0, 0)

        tm_from2 = time(16, 0, 0)
        tm_to2 = time(20, 0, 0)

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.employee2.id: {
                        'workdays': [
                            {
                                'dt': Converter.convert_date(dt),
                                'type': 'W',
                                'dttm_work_start': Converter.convert_datetime(datetime.combine(dt, tm_from1)),
                                'dttm_work_end': Converter.convert_datetime(datetime.combine(dt, tm_to1)),
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                            {
                                'dt': Converter.convert_date(dt),
                                'type': 'W',
                                'dttm_work_start': Converter.convert_datetime(datetime.combine(dt, tm_from2)),
                                'dttm_work_end': Converter.convert_datetime(datetime.combine(dt, tm_to2)),
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                            {
                                'dt': Converter.convert_date(dt + timedelta(1)),
                                'type': 'H',
                                'dttm_work_start': None,
                                'dttm_work_end': None,
                                'details': [],
                            },
                            {
                                'dt': Converter.convert_date(dt + timedelta(2)),
                                'type': 'W',
                                'dttm_work_start': Converter.convert_datetime(datetime.combine(dt + timedelta(2), tm_from1)),
                                'dttm_work_end': Converter.convert_datetime(datetime.combine(dt + timedelta(2), tm_to2)),
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                            {
                                'dt': Converter.convert_date(dt + timedelta(3)),
                                'type': 'W',
                                'dttm_work_start': Converter.convert_datetime(datetime.combine(dt + timedelta(3), tm_from1)),
                                'dttm_work_end': Converter.convert_datetime(datetime.combine(dt + timedelta(3), tm_to2)),
                                'details': [{
                                    'work_type_id': self.work_type2.id,
                                    'percent': 100,
                                }]
                            },
                        ]
                    },
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.filter(
            shop=self.shop,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            dt=dt,
            employee_id=self.employee2.id,
        ).count(), 2)

    @expectedFailure  # TODO: отдельная алгоритм расчета рекомендуемой нормы для автосоставления? Или доп. признак в типе дня?
    def test_create_tt_full_month_with_vacation_is_work_hours_true_and_is_reduce_norm_false(self):
        WorkerDayType.objects.filter(code=WorkerDay.TYPE_VACATION).update(
            is_work_hours=True,
            is_reduce_norm=False,
        )
        dt_from = date(2021, 2, 1)
        dt_to = date(2021, 2, 28)
        dt = dt_from
        for day in range(3):
            dt = dt + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                employee=self.employment2.employee,
                shop=self.employment2.shop,
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )
            self.assertEqual(wd.work_hours.total_seconds()/3600, 5.392857142777778)
        data = self._test_create_tt(dt_from, dt_to)

        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.employee2.id, data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.employee3.id, data['cashiers']))[0]
        self.assertEqual(round(employment2Info['norm_work_amount'], 5), round(134.82142857142856, 5))
        self.assertEqual(employment3Info['norm_work_amount'], 151.0)
