import json
from datetime import datetime, time, date, timedelta
from dateutil.relativedelta import relativedelta

from django.test import override_settings
from django.utils.timezone import now
from rest_framework.test import APITestCase
from unittest.mock import patch
import requests

from src.timetable.models import ShopMonthStat, WorkerDay, WorkerDayCashboxDetails, WorkType, WorkTypeName, EmploymentWorkType
from src.forecast.models import OperationType, OperationTypeName
from src.base.models import Break, WorkerPosition
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

        create_departments_and_users(self)
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

    def test_create_tt(self):
        dt_from = date.today() + timedelta(days=1)

        for day in range(4):
            dt_from = dt_from + timedelta(days=1)
            wd = WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
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
        for day in range(3):
            dt_from = dt_from + timedelta(days=1)
            WorkerDay.objects.create(
                employment=self.employment2,
                worker=self.employment2.user,
                shop=self.employment2.shop,
                dt=dt_from,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=False,
            )
        self.employment6.position = self.position
        self.employment6.save()
        EmploymentWorkType.objects.create(employment=self.employment2, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment3, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment4, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment6, work_type=self.work_type)
        EmploymentWorkType.objects.create(employment=self.employment7, work_type=self.work_type)
        dt_to = (date.today() + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
        wd = WorkerDay.objects.create(
            employment=self.employment3,
            worker=self.employment3.user,
            shop=self.employment3.shop,
            dt=dt_to,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_from, time(9)),
            dttm_work_end=datetime.combine(dt_from, time(22)),
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd
        )
        class res:
            def json(self):
                return {'task_id': 1}
        with patch.object(requests, 'post', return_value=res()) as mock_post:
            response = self.client.post(
                '/rest_api/auto_settings/create_timetable/',
                {
                    'shop_id': self.shop.id,
                    'dt_from': date.today() + timedelta(days=2),
                    'dt_to': dt_to,
                    'use_not_approved': True,
                }
            )
            data = json.loads(mock_post.call_args.kwargs['data'])
            self.assertEqual(response.status_code, 200)
        employment2Info = list(filter(lambda x: x['general_info']['id'] == self.user2.id,data['cashiers']))[0]
        employment3Info = list(filter(lambda x: x['general_info']['id'] == self.user3.id,data['cashiers']))[0]
        self.assertEqual(len(data['work_types']), 2)
        self.assertEqual(len(data['cashiers']), 5)
        self.assertEqual(len(employment2Info['workdays']), min(4, (dt_to - (date.today() + timedelta(days=1))).days))
        self.assertEqual(employment2Info['workdays'][0]['dt'], (date.today() + timedelta(days=2)).strftime('%Y-%m-%d'))
        self.assertEqual(employment3Info['workdays'][-1]['dt'], dt_to.strftime('%Y-%m-%d'))
        self.assertEqual(len(data['algo_params']['breaks_triplets']), 2)
        self.assertIsNotNone(data['algo_params']['breaks_triplets'].get(str(self.position.id)))
        self.assertIsNone(data['algo_params']['breaks_triplets'].get(str(self.unused_position.id)))
