from datetime import timedelta, time, datetime, date

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import FunctionGroup, Network
from src.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


class TestWorkerDay(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()

        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            parent_worker_day=self.worker_day_plan_approved
        )
        self.worker_day_fact_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30, 0)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            parent_worker_day=self.worker_day_fact_approved
        )

        self.client.force_authenticate(user=self.user1)
        self.network.allowed_interval_for_late_arrival = timedelta(minutes=15)
        self.network.allowed_interval_for_early_departure = timedelta(minutes=15)
        self.network.save()

    def test_get_list(self):
        dt = Converter.convert_date(self.dt)

        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&dt={dt}')
        self.assertEqual(len(response.json()), 4)

        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_fact=1&dt={dt}')
        self.assertEqual(len(response.json()), 2)

        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_fact=0&dt={dt}')
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.worker_day_plan_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.worker_day_plan_not_approved.id,
            'shop_id': self.shop.id,
            'worker_id': self.user2.id,
            'employment_id': self.employment2.id,
            'is_fact': False,
            'is_approved': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'parent_worker_day_id': self.worker_day_plan_approved.id,
            'comment': None,
            'dt': Converter.convert_date(self.dt),
            'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'work_hours': '10:45:00',
            'worker_day_details': [],
            'is_outsource': False,
            'is_vacancy': False,
        }

        self.assertEqual(response.json(), data)

    def test_approve(self):
        # Approve plan
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=2),
            'is_fact': False,
            # 'wd_types': WorkerDay.TYPES_USED,  # временно
        }
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).is_approved, True)
        # self.assertIsNone(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).parent_worker_day_id)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())
        # self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).parent_worker_day_id,
        #                  self.worker_day_plan_not_approved.id)

        # Approve fact
        data['is_fact'] = True

        # plan(approved) <- fact0(approved) <- fact1(not approved) ==> plan(approved) <- fact1(approved)
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())
        # self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id,
        #                  self.worker_day_plan_not_approved.id)

    # Последовательное создание и подтверждение P1 -> A1 -> P2 -> F1 -> A2 -> F2
    def test_create_and_approve(self):
        GroupWorkerDayPermission.objects.filter(
            group=self.admin_group,
            worker_day_permission__action=WorkerDayPermission.APPROVE,
        ).delete()
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)

        # create not approved fact
        data['is_fact'] = True
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']

        # edit not approved plan
        data_holiday = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_HOLIDAY,
        }

        response = self.client.put(f"{self.url}{plan_id}/", data_holiday, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], plan_id)
        self.assertEqual(response.json()['type'], data_holiday['type'])

        # edit not approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(7, 48, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(20, 2, 0)))

        response = self.client.put(f"{self.url}{fact_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], fact_id)
        self.assertEqual(response.json()['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(response.json()['dttm_work_end'], data['dttm_work_end'])

        # Approve plan
        approve_dt_from = dt - timedelta(days=5)
        approve_dt_to = dt + timedelta(days=2)
        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': approve_dt_from,
            'dt_to': approve_dt_to,
            'is_fact': False,
            'wd_types': WorkerDay.TYPES_USED,
        }

        response = self.client.post(self.url_approve, data_approve, format='json')
        # если нету ни одного разрешения для action=approve, то ответ -- 403
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        gwdp = GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type=WorkerDay.TYPE_HOLIDAY,
            ),
            limit_days_in_past=3,
            limit_days_in_future=1,
        )
        response = self.client.post(self.url_approve, data_approve, format='json')
        # разрешено изменять день только на 1 день в будущем
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertDictEqual(
            response.json(),
            {
                'detail': 'У вас нет прав на подтверждения типа дня "Выходной" в выбранные '
                          'даты. Необходимо изменить интервал для подтверждения. '
                          'Разрешенный интевал для подтверждения: '
                          f'с {Converter.convert_date(self.dt - timedelta(days=gwdp.limit_days_in_past))} '
                          f'по {Converter.convert_date(self.dt + timedelta(days=gwdp.limit_days_in_future))}'
            }
        )

        gwdp.limit_days_in_past = 10
        gwdp.limit_days_in_future = 5
        gwdp.save()

        response = self.client.post(self.url_approve, data_approve, format='json')
        # проверка наличия прав на редактирование переданных типов дней
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertDictEqual(
            response.json(),
            {
                'detail': 'У вас нет прав на подтверждение типа дня "Рабочий день"'
            }
        )

        for wdp in WorkerDayPermission.objects.filter(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN):
            GroupWorkerDayPermission.objects.get_or_create(
                group=self.admin_group,
                worker_day_permission=wdp,
            )

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(WorkerDay.objects.get(id=plan_id).is_approved, True)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, False)

        # Approve fact
        data_approve['is_fact'] = True

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.is_approved, False)

        for wdp in WorkerDayPermission.objects.filter(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.FACT):
            GroupWorkerDayPermission.objects.get_or_create(
                group=self.admin_group,
                worker_day_permission=wdp,
            )

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, True)

        # create approved plan
        data['is_fact'] = False
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_plan_id = response.json()['id']
        new_plan = WorkerDay.objects.get(id=new_plan_id)
        self.assertNotEqual(new_plan_id, plan_id)
        self.assertEqual(response.json()['type'], data['type'])

        # # create approved plan again
        # response = self.client.post(f"{self.url}", data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

        # edit approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(8, 8, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(21, 2, 0)))

        data['is_fact'] = True
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        res = response.json()
        new_fact_id = res['id']
        new_fact = WorkerDay.objects.get(id=new_fact_id)
        self.assertNotEqual(new_fact_id, fact_id)
        self.assertEqual(res['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(res['dttm_work_end'], data['dttm_work_end'])

        # # create approved fact again
        # response = self.client.post(f"{self.url}", data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

    def test_empty_params(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": []
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_not_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'worker_day_details': ['Это поле обязательно.']})

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_BUSINESS_TRIP,
            # "dttm_work_start": None,
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_not_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'dttm_work_start': ['Это поле обязательно.']})

    def test_edit_approved_wd_secondly(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": 1}
            ]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(),
                         {'error': ['Нельзя менять подтвержденную версию.']}
                         )

        response = self.client.put(f"{self.url}{self.worker_day_fact_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': ['Нельзя менять подтвержденную версию.']})

    def test_edit_worker_day(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 2)

    def test_edit_worker_day_with_shop_code_and_username(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_code": self.shop.code,
            "username": self.user2.username,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 2)

    def test_delete(self):
        # План подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': 'Нельзя удалить подтвержденную версию.'})

        # План неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())

        # Факт подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': 'Нельзя удалить подтвержденную версию.'})

        # Факт неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_not_approved.id).exists())

    def test_S_type_plan_approved_returned_in_tabel_if_fact_approved_is_missing(self):
        WorkerDay.objects.filter(
            id=self.worker_day_plan_approved.id,
        ).update(type=WorkerDay.TYPE_SICK)
        WorkerDay.objects.filter(
            id=self.worker_day_fact_approved.id,  # не удаляется, поэтому обновим дату на другой день
        ).update(parent_worker_day=None, dt=self.dt - timedelta(days=365))

        get_params = {
            'shop_id': self.shop.id,
            'limit': 100,
            'is_tabel': 'true',
            'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt__lte': self.dt.strftime('%Y-%m-%d'),
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'S')

    def _test_tabel(self, plan_start, plan_end, fact_start, fact_end, expected_start, expected_end, expected_hours,
                    extra_get_params=None, tabel_kwarg='is_tabel'):
        plan_dttm_work_start = plan_start
        plan_dttm_work_end = plan_end
        WorkerDay.objects.filter(
            id=self.worker_day_plan_approved.id,
        ).update(
            dttm_work_start=plan_dttm_work_start,
            dttm_work_end=plan_dttm_work_end,
        )
        fact_dttm_work_start = fact_start
        fact_dttm_work_end = fact_end
        self.worker_day_fact_approved.dttm_work_start = fact_dttm_work_start
        self.worker_day_fact_approved.dttm_work_end = fact_dttm_work_end
        self.worker_day_fact_approved.save()
        get_params = {'shop_id': self.shop.id, 'limit': 100, 'hours_details': 'true',
                      'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
                      'dt__lte': self.dt.strftime('%Y-%m-%d'), tabel_kwarg: 'true'}
        get_params.update(extra_get_params or {})
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'W')
        self.assertEqual(resp_data[0]['dttm_work_start'], Converter.convert_datetime(expected_start))
        self.assertEqual(resp_data[0]['dttm_work_end'], Converter.convert_datetime(expected_end))
        self.assertEqual(resp_data[0]['work_hours'], expected_hours)
        return resp_data

    def test_tabel_early_arrival_and_late_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(12, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(11, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=7.0,
        )

    def test_tabel_late_arrival_and_late_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(9, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(11, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=8.0,
        )

    def test_tabel_early_arrival_and_early_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(11, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=8.0,
        )

    def test_tabel_allowed_late_arrival(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(10, 7, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=8.75,
        )

    def test_tabel_allowed_early_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(21, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(9, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 53, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=9.75,
        )

    def test_can_override_tabel_settings(self):
        Network.objects.filter(id=self.network.id).update(
            allowed_interval_for_late_arrival=timedelta(seconds=0),
            allowed_interval_for_early_departure=timedelta(seconds=0),
        )
        self.network.refresh_from_db()

        plan_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(21, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(9, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 53, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=9.63,
        )

    def test_get_hours_details_for_tabel(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(16, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(16, 40, 0))
        fact_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 20, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=9.09,
            extra_get_params=dict(
                hours_details=True,
            )
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 4.71, 'N': 4.38}, resp_data[0]['work_hours_details'])

    def test_get_fact_tabel(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(12, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(17, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 0, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=8.76,
            extra_get_params=dict(
                hours_details=True,
            ),
            tabel_kwarg='fact_tabel',
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 4.38, 'N': 4.38}, resp_data[0]['work_hours_details'])

    def test_get_fact_tabel2(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(12, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(23, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(18, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(23, 0, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=4.5,
            extra_get_params=dict(
                hours_details=True,
            ),
            tabel_kwarg='fact_tabel',
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 3.75, 'N': 0.75}, resp_data[0]['work_hours_details'])

    def test_get_fact_tabel3(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(18, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(9, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(18, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(9, 0, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=13.76,
            extra_get_params=dict(
                hours_details=True,
            ),
            tabel_kwarg='fact_tabel',
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 6.38, 'N': 7.38}, resp_data[0]['work_hours_details'])

    def test_get_worker_day_by_worker__username__in(self):
        get_params = {
            'worker__username__in': self.user2.username,
            'is_fact': 'true',
            'is_approved': 'true',
            'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt__lte': self.dt.strftime('%Y-%m-%d'),
            'by_code': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)

    def test_can_create_and_update_not_approved_fact_only_with_empty_or_workday_type(self):
        dt = now().date()
        data = {
            "shop_code": self.shop.code,
            "username": self.user2.username,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": 'true',
            "type": WorkerDay.TYPE_HOLIDAY,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, 400)

        data['type'] = WorkerDay.TYPE_EMPTY
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        wd_id = response.json()['id']
        self.assertEqual(WorkerDay.objects.filter(id=wd_id).count(), 1)

        data['type'] = WorkerDay.TYPE_WORKDAY
        data['dttm_work_start'] = datetime.combine(dt, time(8, 0, 0))
        data['dttm_work_end'] = datetime.combine(dt, time(20, 0, 0))
        response = self.client.put(f"{self.url}{wd_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def _test_wd_perm(self, url, method, action, graph_type=None, wd_type=None):
        assert method == 'delete' or (graph_type and wd_type)
        GroupWorkerDayPermission.objects.all().delete()

        dt = self.dt + timedelta(days=1)
        if method == 'delete':
            data = None
        else:
            data = {
                "shop_id": self.shop.id,
                "worker_id": self.user2.id,
                "employment_id": self.employment2.id,
                "dt": dt,
                "is_fact": True if graph_type == WorkerDayPermission.FACT else False,
                "type": wd_type,
            }
            if wd_type == WorkerDay.TYPE_WORKDAY:
                data.update({
                    "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
                    "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                })

        response = getattr(self.client, method)(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=action,
                graph_type=graph_type,
                wd_type=wd_type,
            )
        )
        response = getattr(self.client, method)(url, data, format='json')
        method_to_status_mapping = {
            'post': status.HTTP_201_CREATED,
            'put': status.HTTP_200_OK,
            'delete': status.HTTP_204_NO_CONTENT,
        }
        self.assertEqual(response.status_code, method_to_status_mapping.get(method))

    def test_worker_day_permissions(self):
        # create
        self._test_wd_perm(
            self.url, 'post', WorkerDayPermission.CREATE_OR_UPDATE, WorkerDayPermission.PLAN, WorkerDay.TYPE_WORKDAY)
        wd = WorkerDay.objects.last()

        # update
        self._test_wd_perm(
            f"{self.url}{wd.id}/", 'put',
            WorkerDayPermission.CREATE_OR_UPDATE, WorkerDayPermission.PLAN, WorkerDay.TYPE_HOLIDAY,
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type, WorkerDay.TYPE_HOLIDAY)

        # delete
        self._test_wd_perm(
            f"{self.url}{wd.id}/", 'delete',
            WorkerDayPermission.DELETE,
            WorkerDayPermission.PLAN,
            wd.type,
        )

    def test_cant_create_worker_day_with_shop_mismatch(self):
        dt = self.dt + timedelta(days=1)

        shop2_work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop2,
        )

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": shop2_work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['worker_day_details'][0], 'Магазин в типе работ и в рабочем дне должен совпадать.')

    def test_cant_create_worker_day_with_worker_mismatch(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment3.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['employment'][0], 'Сотрудник в трудоустройстве и в рабочем дне должны совпадать.')

    def test_change_range(self):
        data = {
          "ranges": [
            {
              "worker": self.user2.tabel_code,
              "dt_from": self.dt - timedelta(days=10),
              "dt_to": self.dt + timedelta(days=10),
              "type": WorkerDay.TYPE_MATERNITY,
              "is_fact": False,
              "is_approved": True
            }
          ]
        }
        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.user2.tabel_code: {'created_count': 21, 'deleted_count': 1, 'existing_count': 0}}
        )
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())
        self.assertEqual(
            WorkerDay.objects.filter(worker__tabel_code=self.user2.tabel_code, type=WorkerDay.TYPE_MATERNITY).count(),
            21,
        )

        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.user2.tabel_code: {'created_count': 0, 'deleted_count': 0, 'existing_count': 21}}
        )

        wd_without_created_by = WorkerDay.objects.create(
            worker=self.user2,
            dt=self.dt,
            is_fact=False,
            is_approved=True,
            type=WorkerDay.TYPE_MATERNITY,
        )
        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.user2.tabel_code: {'created_count': 0, 'deleted_count': 1, 'existing_count': 21}}
        )
        self.assertFalse(WorkerDay.objects.filter(id=wd_without_created_by.id).exists())
        wd = WorkerDay.objects.filter(
            worker=self.user2,
            dt=self.dt,
            is_fact=False,
            is_approved=True,
            type=WorkerDay.TYPE_MATERNITY,
        ).last()
        self.assertIsNotNone(wd.created_by)
        self.assertEqual(wd.created_by.id, self.user1.id)


class TestWorkerDayCreateFact(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        create_departments_and_users(self)

        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()
        self.work_type_name = WorkTypeName.objects.create(name='Магазин')
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)

        self.client.force_authenticate(user=self.user1)

    def test_create_fact(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved fact
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']

        # create not approved plan
        data['is_fact'] = False
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']


@override_settings(TRUST_TICK_REQUEST=True)
class TestAttendanceRecords(TestsHelperMixin, APITestCase):
    def setUp(self):
        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()

        create_departments_and_users(self)

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            parent_worker_day=self.worker_day_plan_approved
        )
        self.worker_day_fact_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 12, 23)),
            dttm_work_end=datetime.combine(self.dt, time(20, 2, 1)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            parent_worker_day=self.worker_day_fact_approved
        )

    def test_attendancerecords_update(self):
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        tm_end = datetime.combine(self.dt, time(21, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start)

        tm_start2 = datetime.combine(self.dt, time(7, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start2,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        # проверяем, что время начала рабочего дня не перезаписалось
        self.assertNotEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start2)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start)

        AttendanceRecords.objects.create(
            dttm=tm_end,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_end, tm_end)

    def test_attendancerecords_create(self):
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            worker=self.user3
        )
        self.assertFalse(wd.exists())
        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user3
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            worker=self.user3
        )

        self.assertTrue(wd.exists())
        wd = wd.first()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(21, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user3
        )
        self.assertEqual(WorkerDay.objects.get(id=wd.id).dttm_work_end, datetime.combine(self.dt, time(21, 0, 0)))

    def test_attendancerecords_not_approved_fact_create(self):
        self.worker_day_fact_not_approved.parent_worker_day_id = self.worker_day_fact_approved.parent_worker_day_id
        self.worker_day_fact_not_approved.save()

        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            worker=self.user2
        )

        self.assertTrue(wd.exists())

    @override_settings(MDA_SKIP_LEAVING_TICK=False)
    def test_attendancerecords_no_fact_create(self):
        self.worker_day_fact_not_approved.delete()
        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(20, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(20, 0, 0)),
            dttm_work_end=None,
            worker=self.user2
        )

        self.assertTrue(wd.exists())
        wd = wd.first()

        ar = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt + timedelta(days=1), time(6, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.dttm_work_end, ar.dttm)

        wd.dttm_work_end = None
        wd.save()
        ar2 = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt + timedelta(days=3), time(20, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )

        new_wd = WorkerDay.objects.filter(
            dt=self.dt + timedelta(days=3),
            is_fact=True,
            is_approved=True,
            dttm_work_start=None,
            dttm_work_end=ar2.dttm,
            worker=self.user2
        ).first()
        self.assertIsNotNone(new_wd)
        self.assertTrue(new_wd.employment.id, self.employment2.id)

    def test_set_workday_type_for_existing_empty_types(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).update(
            type=WorkerDay.TYPE_EMPTY,
            dttm_work_start=None,
            dttm_work_end=None,
        )

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        fact = WorkerDay.objects.get(id=self.worker_day_fact_approved.id)
        self.assertEqual(fact.type, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(fact.dttm_work_start, tm_start)
        self.assertEqual(fact.dttm_work_end, None)


class TestVacancy(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/vacancy/'
        cls.create_departments_and_users()
        cls.dt_now = date.today()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        cls.network = Network.objects.create(
            primary_color='#BDF82',
            secondary_color='#390AC',
        )
        cls.shop.network = cls.network
        cls.shop.save()
        cls.user2.network = cls.network
        cls.user2.save()
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.vacancy = WorkerDay.objects.create(
            shop=cls.shop,
            worker=cls.user1,
            employment=cls.employment1,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(20)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
        )
        cls.vacancy2 = WorkerDay.objects.create(
            shop=cls.shop,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(17)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
            is_approved=True,
        )
        cls.vac_wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy2,
            work_part=1,
        )
        cls.wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy,
            work_part=0.5,
        )
        cls.wd_details2 = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy,
            work_part=0.5,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_vacancy(self):
        data = {
            'id': None,
            'dt': Converter.convert_date(self.dt_now),
            'dttm_work_start': datetime.combine(self.dt_now, time(hour=11, minute=30)),
            'dttm_work_end': datetime.combine(self.dt_now, time(hour=20, minute=30)),
            'is_fact': False,
            'is_vacancy': True,
            'shop_id': self.shop.id,
            'type': "W",
            'worker_day_details': [
                {
                    'work_part': 1,
                    'work_type_id': self.work_type1.id
                },
            ],
            'worker_id': None
        }

        resp = self.client.post(reverse('WorkerDay-list'), data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def _test_vacancy_ordering(self, ordering_field, desc):
        if getattr(self.vacancy, ordering_field) == getattr(self.vacancy2, ordering_field):
            return

        ordering = ordering_field
        v1_first = getattr(self.vacancy, ordering_field) < getattr(self.vacancy2, ordering_field)
        if desc:
            ordering = '-' + ordering_field
            v1_first = not v1_first
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100&ordering={ordering}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], (self.vacancy if v1_first else self.vacancy2).id)
        self.assertEqual(resp.json()['results'][-1]['id'], (self.vacancy2 if v1_first else self.vacancy).id)

    def test_vacancy_ordering(self):
        for ordering_field in ['id', 'dt', 'dttm_work_start', 'dttm_work_end']:
            self._test_vacancy_ordering(ordering_field, desc=False)
            self._test_vacancy_ordering(ordering_field, desc=True)

    def test_default_dt_from_and_dt_to_filers(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dt=self.dt_now - timedelta(days=1))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dt=self.dt_now + timedelta(days=35))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 0)

        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dt=self.dt_now + timedelta(days=27))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_default_vacancy_ordering_is_dttm_work_start_asc(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)))
        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=12, minute=30)))

        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], self.vacancy.id)

        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=12, minute=30)))
        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)))

        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], self.vacancy2.id)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 2)

    def test_get_list_shift_length(self):
        response = self.client.get(
            f'{self.url}?shop_id={self.shop.id}&shift_length_min=7:00:00&shift_length_max=9:00:00&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_vacant_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_vacant=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_confirm_vacancy(self):
        self.shop.__class__.objects.filter(id=self.shop.id).update(email=True)
        pnawd = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)),
            dttm_work_end=datetime.combine(self.dt_now, time(hour=20, minute=30)),
            dt=self.dt_now,
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type1,
            worker_day=pnawd,
            work_part=1,
        )
        pawd = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        self.client.force_authenticate(user=self.user2)
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
        )
        FunctionGroup.objects.create(
            group=self.employee_group,
            method='POST',
            func='WorkerDay_confirm_vacancy',
            level_up=1,
            level_down=99,
        )
        response = self.client.post(f'/rest_api/worker_day/{self.vacancy2.id}/confirm_vacancy/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Изменение в графике выхода сотрудников')

        self.assertFalse(WorkerDay.objects.filter(id=pawd.id).exists())

    def test_approve_vacancy(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(worker_id=None, is_approved=False)
        wd = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())

        WorkerDay.objects.filter(id=self.vacancy.id).update(worker=wd.worker, is_approved=False)

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(WorkerDay.objects.filter(id=wd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.vacancy.id).exists())


class TestAditionalFunctions(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        from src.timetable.models import ExchangeSettings
        super().setUp()

        self.url = '/rest_api/worker_day/'
        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)
        ExchangeSettings.objects.create(network=self.network)
        self.client.force_authenticate(user=self.user1)

    def create_holidays(self, employment, dt_from, count, approved, wds={}):
        result = {}
        for day in range(count):
            dt = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(dt, None)
            result[dt] = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
                shop=employment.shop,
                dt=dt,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
        return result

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm, approved, wds={}):
        result = {}
        for day in range(count):
            date = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(date, None)
            wd = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
                shop=employment.shop,
                dt=date,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(date, time(from_tm)),
                dttm_work_end=datetime.combine(date, time(to_tm)),
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
            result[date] = wd

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        return result

    def test_delete_all(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'dt_from': Converter.convert_date(dt_from),
            'dt_to': Converter.convert_date(dt_from + timedelta(4)),
            'delete_all': True,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        url = f'{self.url}delete_timetable/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        # остаётся 4 т.к. у сотрудника auto_timetable=False
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 4)

    def test_delete(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'dt_from': Converter.convert_date(dt_from),
            'dt_to': Converter.convert_date(dt_from + timedelta(4)),
            'types': ['W', ],
            'users': [self.user2.id, self.user3.id],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 3, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        self.create_holidays(self.employment2, dt_from + timedelta(3), 1, False)
        url = f'{self.url}delete_timetable/'
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        # остаётся 1 выходной т.к. удаляем только рабочие дни
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 1)

    def test_exchange_approved(self):
        dt_from = date.today()
        data = {
            'worker1_id': self.user2.id,
            'worker2_id': self.user3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
            'is_approved': True,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        url = f'{self.url}exchange/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)

    def test_exchange_not_approved(self):
        dt_from = date.today()
        data = {
            'worker1_id': self.user2.id,
            'worker2_id': self.user3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
            'is_approved': False,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        url = f'{self.url}exchange/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)

    def test_duplicate_full(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(worker=self.user2).values_list('id', flat=True)),
            'to_worker_id': self.user3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)
        self.assertEqual(WorkerDay.objects.filter(worker=self.user3, is_approved=False).count(), 5)

    def test_duplicate_less(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(worker=self.user2).values_list('id', flat=True)),
            'to_worker_id': self.user3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 4)
        self.assertEqual(WorkerDay.objects.filter(worker=self.user3, is_approved=False).count(), 5)

    def test_duplicate_more(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(worker=self.user2).values_list('id', flat=True)),
            'to_worker_id': self.user3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(8)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(worker=self.user3, is_approved=False).count(), 8)

    def test_duplicate_for_different_start_dates(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(worker=self.user2).values_list('id', flat=True)),
            'to_worker_id': self.user3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(worker=self.user3, is_approved=False).count(), 8)

    def test_duplicate_day_without_time(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)
        self.create_holidays(self.employment2, dt_from, 1, False)

        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(worker=self.user2).values_list('id', flat=True)),
            'to_worker_id': self.user3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(worker=self.user3, is_approved=False).count(), 8)

    def test_change_list(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'workers': {
                self.user2.id: [
                    Converter.convert_date(dt_from),
                    Converter.convert_date(dt_from + timedelta(1)),
                    Converter.convert_date(dt_from + timedelta(3)),
                ],
                self.user3.id: [
                    Converter.convert_date(dt_from),
                    Converter.convert_date(dt_from + timedelta(2)),
                    Converter.convert_date(dt_from + timedelta(3)),
                ],
            },
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'work_type': self.work_type.id,
            'comment': 'Test change',
        }
        wds = self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment2, dt_from, 2, 10, 20, False, wds=wds)
        wds = self.create_worker_days(self.employment2, dt_from, 3, 10, 20, True)
        wds.update(self.create_holidays(self.employment3, dt_from + timedelta(3), 1, True))
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False, wds=wds)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(len(data[str(self.user2.id)]), 3)
        self.assertEqual(len(data[str(self.user3.id)]), 3)
