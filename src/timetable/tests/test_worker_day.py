import json
import time as time_module
import uuid
from datetime import timedelta, time, datetime, date
from decimal import Decimal
from unittest import mock

from django.db import transaction, IntegrityError
from django.db.models import Q
from django.test import override_settings
from django.utils.timezone import now
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import (
    Network,
    Employment,
    Shop,
    User,
    NetworkConnect,
)
from src.timetable.exceptions import WorkTimeOverlap
from src.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    WorkerDayPermission,
    GroupWorkerDayPermission,
    WorkerDayType,
)
from src.timetable.tests.factories import WorkerDayFactory, WorkerDayTypeFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter


class TestWorkerDay(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/'
        cls.url_approve = '/rest_api/worker_day/approve/'
        cls.dt = (now() + timedelta(hours=3)).date()

        cls.create_departments_and_users()
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop2)

        cls.worker_day_plan_approved = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 0, 0)),
            is_approved=True,
        )
        cls.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 0, 0)),
            parent_worker_day=cls.worker_day_plan_approved
        )
        cls.worker_day_fact_approved = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 30, 0)),
            is_approved=True,
            parent_worker_day=cls.worker_day_plan_approved,
            closest_plan_approved=cls.worker_day_plan_approved,
            last_edited_by=cls.user1,
        )
        cls.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(19, 59, 1)),
            parent_worker_day=cls.worker_day_fact_approved,
            closest_plan_approved=cls.worker_day_plan_approved,
            last_edited_by=cls.user1,
        )
        cls.network.allowed_interval_for_late_arrival = timedelta(minutes=15)
        cls.network.allowed_interval_for_early_departure = timedelta(minutes=15)
        cls.network.crop_work_hours_by_shop_schedule = False
        cls.network.only_fact_hours_that_in_approved_plan = True
        cls.network.save()

        cls.shop.tm_open_dict = f'{{"all":"00:00:00"}}'
        cls.shop.tm_close_dict = f'{{"all":"00:00:00"}}'
        cls.shop.save()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

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
            'code': None,
            'shop_id': self.shop.id,
            'employee_id': self.employee2.id,
            'employment_id': self.employment2.id,
            'is_fact': False,
            'is_approved': False,
            'is_blocked': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'parent_worker_day_id': self.worker_day_plan_approved.id,
            'comment': None,
            'dt': Converter.convert_date(self.dt),
            'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_start_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'dttm_work_end_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'work_hours': '10:45:00',
            'worker_day_details': [],
            'is_outsource': False,
            'outsources': [],
            'is_vacancy': False,
            'unaccounted_overtime': 0.0,
            'crop_work_hours_by_shop_schedule': True,
            'closest_plan_approved_id': None,
            'cost_per_hour': None,
            'total_cost': None,
        }

        self.assertEqual(response.json(), data)

    def test_approve(self):
        # Approve plan
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=2),
            'is_fact': False,
        }
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # не должен подтвердиться, т.к. нету изменений в дне
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).is_approved, False)

        WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).update(
            dttm_work_start=datetime.combine(self.dt, time(8, 30, 0))
        )
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).is_approved, True)

        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())

        # Approve fact
        data['is_fact'] = True

        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertEqual(
            WorkerDay.objects.filter(
                dt=self.worker_day_fact_not_approved.dt, 
                shop=self.worker_day_fact_not_approved.shop,
                employee=self.worker_day_fact_not_approved.employee,
                employment=self.worker_day_fact_not_approved.employment,
                is_approved=False,
                is_fact=True,
            ).first().source, 
            WorkerDay.SOURCE_ON_APPROVE
        )
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())

    def test_approve_open_vacs(self):
        open_vacancy = WorkerDay.objects.create(
            shop=self.shop,
            is_vacancy=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(10)),
            dttm_work_end=datetime.combine(self.dt, time(19)),
        )
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=2),
            'is_fact': False,
        }
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        open_vacancy.refresh_from_db()
        self.assertFalse(open_vacancy.is_approved)
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=2),
            'is_fact': False,
            'approve_open_vacs': True,
        }
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        open_vacancy.refresh_from_db()
        self.assertTrue(open_vacancy.is_approved)


    # Последовательное создание и подтверждение P1 -> A1 -> P2 -> F1 -> A2 -> F2
    def test_create_and_approve(self):
        GroupWorkerDayPermission.objects.filter(
            group=self.admin_group,
            worker_day_permission__action=WorkerDayPermission.APPROVE,
        ).delete()
        dt = self.dt + timedelta(days=1)

        data_holiday = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_HOLIDAY,
        }

        # create not approved plan
        response = self.client.post(self.url, data_holiday, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 0)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).source, WorkerDay.SOURCE_FULL_EDITOR)

        # edit not approved plan
        data = {
            "id": plan_id,
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
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

        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], plan_id)
        self.assertEqual(response.json()['type'], data['type'])
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)

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
                wd_type_id=WorkerDay.TYPE_HOLIDAY,
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
                'detail': 'У вас нет прав на подтверждение типа дня "Выходной" в выбранные '
                          'даты. Необходимо изменить даты. '
                          'Разрешенный интервал: '
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

        data_approve['wd_types'] = [WorkerDay.TYPE_HOLIDAY]
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # день не должен подтвердиться, т.к. передан тип только выходной, а у нас рабочий день
        self.assertEqual(WorkerDay.objects.get(id=plan_id).is_approved, False)

        data_approve['wd_types'] = WorkerDay.TYPES_USED
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).is_approved, True)

        # create not approved fact
        data['is_fact'] = True
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']
        data['id'] = fact_id

        # edit not approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(7, 48, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(20, 2, 0)))

        response = self.client.put(f"{self.url}{fact_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], fact_id)
        self.assertEqual(response.json()['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(response.json()['dttm_work_end'], data['dttm_work_end'])

        # Approve plan again to check fact is not approved
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
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

        # cant create approved plan again
        data['is_fact'] = False
        data.pop('id')
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertContains(
            response, 'Операция не может быть выполнена. Недопустимое пересечение времени работы',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

        # # create approved plan again
        # response = self.client.post(f"{self.url}", data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

        # edit approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(8, 8, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(21, 2, 0)))

        data['is_fact'] = True
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertContains(
            response, 'Операция не может быть выполнена. Недопустимое пересечение времени работы',
            status_code=status.HTTP_400_BAD_REQUEST,
        )

        # # create approved fact again
        # response = self.client.post(f"{self.url}", data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

    def test_approve_fact_when_approved_and_not_approved_version_differs_only_by_end_time(self):
        WorkerDay.objects.filter(
            id=self.worker_day_fact_approved.id,
        ).update(
            dttm_work_start=datetime.combine(self.worker_day_fact_approved.dt, time(10)),
            dttm_work_end=None,
        )
        WorkerDay.objects.filter(
            id=self.worker_day_fact_not_approved.id,
        ).update(
            dttm_work_start=datetime.combine(self.worker_day_fact_not_approved.dt, time(10)),
            dttm_work_end=datetime.combine(self.worker_day_fact_not_approved.dt, time(19)),
        )

        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': self.worker_day_fact_approved.dt,
            'dt_to': self.worker_day_fact_approved.dt,
            'is_fact': True,
            'wd_types': WorkerDay.TYPES_USED,
        }

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())

    @staticmethod
    def _create_att_record(type, dttm, user_id, employee_id, shop_id, terminal=True):
        return AttendanceRecords.objects.create(
            dttm=dttm,
            shop_id=shop_id,
            user_id=user_id,
            employee_id=employee_id,
            type=type,
            terminal=terminal,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_recalc_fact_from_records_after_approve(self):
        self.network.run_recalc_fact_from_att_records_on_plan_approve = True
        self.network.save()
        WorkerDay.objects.all().delete()
        dt = date.today()
        wd_plan1 = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, time(18)),
            dttm_work_end=datetime.combine(dt + timedelta(1), time(1)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
        )
        wd_plan2 = WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, time(12)),
            dttm_work_end=datetime.combine(dt, time(22)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
        )
        self._create_att_record(AttendanceRecords.TYPE_COMING, datetime.combine(dt, time(17, 49)), self.user2.id, self.employee2.id, self.shop.id, terminal=False)
        self._create_att_record(AttendanceRecords.TYPE_COMING, datetime.combine(dt + timedelta(1), time(1, 5)), self.user2.id, self.employee2.id, self.shop.id)
        self._create_att_record(AttendanceRecords.TYPE_COMING, datetime.combine(dt, time(11, 56)), self.user3.id, self.employee3.id, self.shop.id, terminal=False)
        self._create_att_record(AttendanceRecords.TYPE_LEAVING, datetime.combine(dt, time(23, 1)), self.user3.id, self.employee3.id, self.shop.id)

        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, source=WorkerDay.SOURCE_AUTO_FACT).count(), 3)
        data = {
            'shop_id': self.shop.id,
            'dt_from': dt,
            'dt_to': dt + timedelta(days=1),
            'is_fact': False,
        }
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 2)
        wd_night_shift = WorkerDay.objects.get(employee=self.employee2, is_fact=True, is_approved=True)
        self.assertEqual(wd_night_shift.source, WorkerDay.RECALC_FACT_FROM_ATT_RECORDS)
        self.assertEqual(wd_night_shift.dttm_work_start, datetime.combine(dt, time(17, 49)))
        self.assertEqual(wd_night_shift.dttm_work_end, datetime.combine(dt + timedelta(1), time(1, 5)))
        self.assertEqual(AttendanceRecords.objects.filter(type=AttendanceRecords.TYPE_COMING).count(), 2)
        self.assertEqual(AttendanceRecords.objects.filter(type=AttendanceRecords.TYPE_LEAVING).count(), 2)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_recalc_fact_from_records_after_approve_with_multiple_wdays_in_plan(self):
        """
        Отметки:
        10:11 приход
        14:14 уход
        18:25 приход
        22:12 уход

        1. Сначала нету плана -> 1 workeday в факте
        2. Добавляем план подтверждаем -> происходит пересчет факта на основе отметок, создается 2 wd в факте
        """
        self.network.run_recalc_fact_from_att_records_on_plan_approve = True
        self.network.save()
        WorkerDay.objects.all().delete()

        dt = date.today()
        self._create_att_record(AttendanceRecords.TYPE_COMING, datetime.combine(dt, time(10, 11)), self.user2.id,
                          self.employee2.id, self.shop.id, terminal=False)
        self._create_att_record(AttendanceRecords.TYPE_LEAVING, datetime.combine(dt, time(14, 14)), self.user2.id,
                          self.employee2.id, self.shop.id, terminal=False)
        self._create_att_record(AttendanceRecords.TYPE_COMING, datetime.combine(dt, time(18, 25)), self.user2.id,
                          self.employee2.id, self.shop.id, terminal=False)
        self._create_att_record(AttendanceRecords.TYPE_LEAVING, datetime.combine(dt, time(22, 12)), self.user2.id,
                          self.employee2.id, self.shop.id, terminal=False)

        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)

        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(dt, time(10, 11)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(dt, time(22, 12)))

        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(14)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=False,
            is_fact=False,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, time(18)),
            dttm_work_end=datetime.combine(dt, time(22)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=False,
            is_fact=False,
        )

        data = {
            'shop_id': self.shop.id,
            'dt_from': dt,
            'dt_to': dt,
            'is_fact': False,
        }
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 2)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_edit_manual_fact_on_recalc_fact_from_att_records_is_working(self):
        """
        1. Включены настройки "Считать только те фактические часы,
         которые есть в подтвержденном плановом графике"
         и "Запускать пересчет факта на основе отметок при подтверждении плана".
        2. У сотрудника подтвержденный план 12:00-20:00.
        3. Сотрудник в УРВ отметился в 10:59 на приход и в 19:05 на уход.
        4. Директор/супервайзер изменил факт на 11:00-19:00 и подтвердил факт.
        5. Директор/супервайзер изменил план с 12:00-20:00 на 11:00-19:00, подтвердил.
            При этом запустился пересчет фактического графика на основе отметок.
        5.1. При включенной настройке "Изменять ручные корректировки при пересчете факта на основе отметок (при подтверждения плана)"
            факт, скорректированный вручную, скорректируется на основе отметоки снова станет раным 10:59-19:05.
        5.2. При выключенной настройке "Изменять ручные корректировки при пересчете факта на основе отметок (при подтверждения плана)"
            факт, скорректированный вручную, будет пропущен и останется 11:00-19:00
        """
        self.network.run_recalc_fact_from_att_records_on_plan_approve = True
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        WorkerDay.objects.all().delete()

        today = date.today()
        plan_approved = WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=today,
            dttm_work_start=datetime.combine(today, time(12)),
            dttm_work_end=datetime.combine(today, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=True,
            is_fact=False,
        )
        plan_not_approved = WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=today,
            dttm_work_start=datetime.combine(today, time(12)),
            dttm_work_end=datetime.combine(today, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=False,
            is_fact=False,
        )
        self._create_att_record(
            AttendanceRecords.TYPE_COMING, datetime.combine(today, time(10, 59)), self.user2.id, self.employee2.id,
            self.shop.id, terminal=False)
        self._create_att_record(
            AttendanceRecords.TYPE_LEAVING, datetime.combine(today, time(19, 5)), self.user2.id, self.employee2.id,
            self.shop.id, terminal=False)

        fact_approved = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertIsNotNone(fact_approved)
        self.assertEqual(fact_approved.dttm_work_start, datetime.combine(today, time(10, 59)))
        self.assertEqual(fact_approved.dttm_work_end, datetime.combine(today, time(19, 5)))
        self.assertIsNone(fact_approved.last_edited_by_id)
        self.assertEqual(fact_approved.closest_plan_approved_id, plan_approved.id)
        fact_not_approved = WorkerDay.objects.filter(is_fact=True, is_approved=False).first()
        self.assertIsNotNone(fact_not_approved)

        fact_not_approved.last_edited_by_id = self.user1.id
        fact_not_approved.dttm_work_start = datetime.combine(today, time(11))
        fact_not_approved.dttm_work_end = datetime.combine(today, time(19))
        fact_not_approved.save()
        resp = self._approve(self.shop.id, True, today, today)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        fact_not_approved.refresh_from_db()
        self.assertTrue(fact_not_approved.is_approved)
        fact_approved = fact_not_approved  # подтв. версия замещена черновиком
        self.assertEqual(fact_approved.closest_plan_approved_id, plan_approved.id)

        plan_not_approved.dttm_work_start = datetime.combine(today, time(11))
        plan_not_approved.dttm_work_end = datetime.combine(today, time(19))
        plan_not_approved.save()

        try:
            with transaction.atomic():
                resp = self._approve(self.shop.id, False, today, today)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                plan_not_approved.refresh_from_db()
                self.assertTrue(plan_not_approved.is_approved)
                plan_approved = plan_not_approved  # подтв. версия замещена черновиком

                # по умолчанию настройка выключена, т.е. факт не должен измениться
                fact_approved.refresh_from_db()
                self.assertEqual(fact_approved.dttm_work_start, datetime.combine(today, time(11)))
                self.assertEqual(fact_approved.dttm_work_end, datetime.combine(today, time(19)))
                self.assertEqual(fact_approved.closest_plan_approved_id, plan_approved.id)
                raise IntegrityError
        except IntegrityError:
            pass

        try:
            with transaction.atomic():
                self.network.edit_manual_fact_on_recalc_fact_from_att_records = True
                self.network.save()
                resp = self._approve(self.shop.id, False, today, today)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                plan_not_approved.refresh_from_db()
                self.assertTrue(plan_not_approved.is_approved)
                plan_approved = plan_not_approved  # подтв. версия замещена черновиком

                # настройка выключена, т.е. факт должен измениться
                fact_approved.refresh_from_db()
                self.assertEqual(fact_approved.dttm_work_start, datetime.combine(today, time(10, 59)))
                self.assertEqual(fact_approved.dttm_work_end, datetime.combine(today, time(19, 5)))
                self.assertEqual(fact_approved.closest_plan_approved_id, plan_approved.id)
                raise IntegrityError
        except IntegrityError:
            pass

    def test_att_record_fact_type_id_received_from_closest_plan(self):
        WorkerDay.objects.all().delete()
        san_day_wd_type = WorkerDayTypeFactory(
            code='SD',
            name='Санитарный день',
            short_name='C/Д',
            html_color='#f7f7f7',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='СД',
            is_dayoff=False,
            is_work_hours=False,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=True,
            ordering=0,
        )

        today = date.today()
        plan_approved = WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=today,
            dttm_work_start=datetime.combine(today, time(10)),
            dttm_work_end=datetime.combine(today, time(20)),
            type_id=san_day_wd_type.code,
            shop=self.shop,
            is_approved=True,
            is_fact=False,
        )

        self._create_att_record(
            AttendanceRecords.TYPE_COMING, datetime.combine(today, time(10, 2)), self.user2.id, self.employee2.id,
            self.shop.id, terminal=False)
        self._create_att_record(
            AttendanceRecords.TYPE_LEAVING, datetime.combine(today, time(19, 55)), self.user2.id, self.employee2.id,
            self.shop.id, terminal=False)

        fact_approved = WorkerDay.objects.get(is_fact=True, is_approved=True)
        self.assertEqual(fact_approved.closest_plan_approved_id, plan_approved.id)
        self.assertEqual(fact_approved.type_id, san_day_wd_type.code)

    def test_fact_date_fixed_after_plan_approve(self):
        """
        1. план есть только на вчера
        2. происходят отметки сегодня, но ближайших план найден на вчера (факт крепится к вчерашнему дню)
        3. проиходит исправление плана -> факт должен перецепиться на сегодня
        4. holidays deleted if there is workeday
        """
        self.network.run_recalc_fact_from_att_records_on_plan_approve = True
        self.network.save()
        WorkerDay.objects.all().delete()
        today = date.today()
        yesterday = today - timedelta(days=1)
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=yesterday,
            dttm_work_start=datetime.combine(yesterday, time(14)),
            dttm_work_end=datetime.combine(yesterday, time(23)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=True,
            is_fact=False,
        )

        self._create_att_record(AttendanceRecords.TYPE_COMING, datetime.combine(today, time(1, 14)), self.user2.id,
                          self.employee2.id, self.shop.id, terminal=False)
        self._create_att_record(AttendanceRecords.TYPE_LEAVING, datetime.combine(today, time(17, 3)), self.user2.id,
                          self.employee2.id, self.shop.id, terminal=False)

        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)

        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dt, yesterday)

        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=yesterday,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_approved=False,
            is_fact=False,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=today,
            dttm_work_start=datetime.combine(yesterday, time(1)),
            dttm_work_end=datetime.combine(yesterday, time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=False,
            is_fact=False,
        )

        approve_data = {
            'shop_id': self.shop.id,
            'dt_from': yesterday,
            'dt_to': today,
            'is_fact': False,
        }
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            response = self.client.post(self.url_approve, self.dump_data(approve_data), content_type='application/json')

        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)

        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dt, today)

    def test_deleted_holidays_when_there_is_workday(self):
        """Holidays deleted if there is workday."""
        self.network.run_recalc_fact_from_att_records_on_plan_approve = True
        self.network.save()
        WorkerDay.objects.all().delete()
        today = date.today()
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=today,
            dttm_work_start=datetime.combine(today, time(14)),
            dttm_work_end=datetime.combine(today, time(23)),
            type_id=WorkerDay.TYPE_HOLIDAY,
            shop=self.shop,
            is_approved=True,
            is_fact=False,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=today,
            dttm_work_start=datetime.combine(today, time(14)),
            dttm_work_end=datetime.combine(today, time(23)),
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            is_fact=False,
        )
        self.assertEqual(WorkerDay.objects.count(), 2)

        approve_data = {
            'shop_id': self.shop.id,
            'dt_from': today,
            'dt_to': today,
            'is_fact': False
        }

        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            response = self.client.post(self.url_approve, self.dump_data(approve_data), content_type='application/json')

        self.assertEqual(response.status_code, 200)

        self.assertEqual(WorkerDay.objects.count(), 2)  # workday approve & workday not approve

    def test_empty_params(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
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
            "employee_id": self.employee2.id,
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

    def test_copy_approved_to_fact_crossing(self):
        dt_now = date.today()
        WorkerDay.objects.all().delete()
        def create_worker_days(employment, dt_from, count, from_tm, to_tm, approved, wds={}, is_blocked=False, night_shift=False):
            result = {}
            for day in range(count):
                date = dt_from + timedelta(days=day)
                parent_worker_day = None if approved else wds.get(date, None)
                date_to = date + timedelta(1) if night_shift else date
                wd, _ = WorkerDay.objects.update_or_create(
                    employee=employment.employee,
                    shop=employment.shop,
                    dt=date,
                    is_approved=approved,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    is_fact=False,
                    defaults=dict(
                        employment=employment,
                        dttm_work_start=datetime.combine(date, time(from_tm)),
                        dttm_work_end=datetime.combine(date_to, time(to_tm)),
                        parent_worker_day=parent_worker_day,
                        is_blocked=is_blocked,
                    )
                )
                result[date] = wd

                WorkerDayCashboxDetails.objects.create(
                    work_type=self.work_type,
                    worker_day=wd
                )
            return result
        def update_or_create_holidays(employment, dt_from, count, approved, wds={}):
            result = {}
            for day in range(count):
                dt = dt_from + timedelta(days=day)
                parent_worker_day = None if approved else wds.get(dt, None)
                result[dt] = WorkerDay.objects.update_or_create(
                    employee=employment.employee,
                    shop=employment.shop,
                    dt=dt,
                    type_id=WorkerDay.TYPE_HOLIDAY,
                    is_approved=approved,
                    is_fact=False,
                    defaults=dict(
                        employment=employment,
                        parent_worker_day=parent_worker_day,
                    )
                )
            return result
        create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)
        WorkerDay.objects.create(
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            dt=dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop_id=self.employment1.shop_id,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(dt_now, time(8, 35)),
        )
        data = {
            'employee_ids': [
                self.employment1.employee_id,
                self.employment3.employee_id,
            ],
            'dates': [
                dt_now + timedelta(days=i)
                for i in range(6)
            ],
            'type': 'PF',
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 20)
        self.network.copy_plan_to_fact_crossing = True
        self.network.save()
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, source=WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_FACT).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, dt=dt_now, employee_id=self.employment1.employee_id)
        wd_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, dt=dt_now, employee_id=self.employment1.employee_id)
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(dt_now, time(8, 35)))
        self.assertEqual(wd_approved.dttm_work_start, datetime.combine(dt_now, time(8, 35)))
        self.assertEqual(wd_not_approved.dttm_work_end, None)
        self.assertEqual(wd_approved.dttm_work_end, None)

    def test_edit_approved_wd_secondly(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
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
                         {'error': ['You cannot change the approved version.']}
                         )

        response = self.client.put(f"{self.url}{self.worker_day_fact_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': ['You cannot change the approved version.']})

    def test_edit_worker_day(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
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
        self.assertEqual(WorkerDay.objects.get(id=plan_id).source, WorkerDay.SOURCE_INTEGRATION)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 2)


    def test_edit_worker_day_last_edited_by(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
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
        self.assertEqual(WorkerDay.objects.get(id=plan_id).created_by_id, self.user1.id)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).last_edited_by_id, self.user1.id)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        self.client.force_authenticate(user=self.user2)
        self.employment2.function_group = self.admin_group
        self.employment2.save()
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).created_by_id, self.user1.id)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).last_edited_by_id, self.user2.id)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&dt={dt}')
        self.assertEqual(
            response.json()[0]['last_edited_by'],
            {
                'id': self.user2.id,
                'first_name': self.user2.first_name,
                'last_name': self.user2.last_name,
                'middle_name': None,
                'avatar': None,
            }
        )


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
        ).update(type_id=WorkerDay.TYPE_SICK)
        WorkerDay.objects.filter(
            id=self.worker_day_fact_approved.id,  # не удаляется, поэтому обновим дату на другой день
        ).update(parent_worker_day=None, dt=self.dt - timedelta(days=365))

        get_params = {
            'shop_id': self.shop.id,
            'limit': 100,
            'fact_tabel': 'true',
            'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt__lte': self.dt.strftime('%Y-%m-%d'),
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'S')

    def _test_tabel(self, plan_start, plan_end, fact_start, fact_end, expected_start, expected_end, expected_hours,
                    extra_get_params=None, tabel_kwarg='fact_tabel'):
        self.worker_day_plan_approved.shop.network.refresh_from_db()
        self.worker_day_fact_approved.shop.network.refresh_from_db()

        plan_dttm_work_start = plan_start
        plan_dttm_work_end = plan_end
        self.worker_day_plan_approved.dttm_work_start = plan_dttm_work_start
        self.worker_day_plan_approved.dttm_work_end = plan_dttm_work_end
        self.worker_day_plan_approved.save()

        fact_dttm_work_start = fact_start
        fact_dttm_work_end = fact_end
        self.worker_day_fact_approved.dttm_work_start = fact_dttm_work_start
        self.worker_day_fact_approved.dttm_work_end = fact_dttm_work_end
        self.worker_day_fact_approved.save()
        get_params = {'shop_id': self.shop.id, 'limit': 100,
                      'dt__gte': (self.dt - timedelta(days=5)),
                      'dt__lte': self.dt, tabel_kwarg: 'true'}
        get_params.update(extra_get_params or {})
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'W')
        self.assertEqual(resp_data[0]['dttm_work_start_tabel'], Converter.convert_datetime(expected_start))
        self.assertEqual(resp_data[0]['dttm_work_end_tabel'], Converter.convert_datetime(expected_end))
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

    def test_fill_empty_days_param_only_plan_exists_returns_zero_hours_workday(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).delete()
        get_params = {
            'employment__tabel_code__in': self.employee2.tabel_code,
            'dt__gte': self.dt,
            'dt__lte': self.dt,
            'fact_tabel': 'true',
            'fill_empty_days': 'true',
            'hours_details': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['id'], None)
        self.assertEqual(resp_data[0]['type'], WorkerDay.TYPE_WORKDAY)
        self.assertEqual(resp_data[0]['work_hours'], 0)
        self.assertEqual(resp_data[0]['work_hours_details']['D'], 0)

    def test_fill_empty_days_param_only_plan_exists_returns_absense_in_past(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).update(
            dt=self.dt - timedelta(days=1),
            dttm_work_start=self.worker_day_plan_approved.dttm_work_start - timedelta(days=1),
            dttm_work_end=self.worker_day_plan_approved.dttm_work_end - timedelta(days=1),
        )
        get_params = {
            'employment__tabel_code__in': self.employee2.tabel_code,
            'dt__gte': self.dt - timedelta(days=1),
            'dt__lte': self.dt - timedelta(days=1),
            'fact_tabel': 'true',
            'fill_empty_days': 'true',
            'hours_details': 'true',
        }
        with freeze_time(datetime.now() + timedelta(hours=self.shop.get_tz_offset())):
            response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['id'], None)
        self.assertEqual(resp_data[0]['type'], WorkerDay.TYPE_ABSENSE)

    def test_fill_empty_days_param_no_days_exists_returns_holiday(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).delete()
        get_params = {
            'employment__tabel_code__in': self.employee2.tabel_code,
            'dt__gte': self.dt,
            'dt__lte': self.dt,
            'fact_tabel': 'true',
            'fill_empty_days': 'true',
            'hours_details': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], WorkerDay.TYPE_HOLIDAY)

    def test_work_hours_as_decimal_for_plan_approved(self):
        get_params = {'shop_id': self.shop.id,
                      'dt__gte': self.worker_day_plan_approved.dt,
                      'dt__lte': self.worker_day_plan_approved.dt,
                      'is_fact': False, 'is_approved': True}
        resp = self.client.get('/rest_api/worker_day/', data=get_params)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['work_hours'], 10.75)

    def test_get_hours_details_for_plan_approved(self):
        get_params = {'shop_id': self.shop.id,
                      'dt__gte': self.worker_day_plan_approved.dt,
                      'dt__lte': self.worker_day_plan_approved.dt,
                      'is_fact': False, 'is_approved': True, 'hours_details': True}
        resp = self.client.get('/rest_api/worker_day/', data=get_params)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['work_hours'], 10.75)
        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 10.75, 'N': 0.0}, resp_data[0]['work_hours_details'])

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
            'dt__gte': (self.dt - timedelta(days=5)),
            'dt__lte': self.dt,
            'by_code': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)

    def test_can_create_and_update_not_approved_fact_only_with_empty_or_workday_type(self):
        WorkerDay.objects.all().delete()
        dt = now().date()
        data = {
            "shop_code": self.shop.code,
            "username": self.user2.username,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_HOLIDAY,
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ],
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

        # create plan
        data['is_fact'] = False
        response = self.client.put(f"{self.url}{wd_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # approve plan
        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': dt,
            'dt_to': dt,
            'is_fact': False,
        }
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # create fact
        data['is_fact'] = True
        response = self.client.put(f"{self.url}{wd_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def _test_wd_perm(self, url, method, action, graph_type=None, wd_type=None, prev_wd_type=None):
        assert method == 'delete' or (graph_type and wd_type)
        GroupWorkerDayPermission.objects.all().delete()

        dt = self.dt + timedelta(days=1)
        if method == 'delete':
            data = None
        else:
            data = {
                "shop_id": self.shop.id,
                "employee_id": self.employee2.id,
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
        if action == WorkerDayPermission.UPDATE and prev_wd_type != wd_type:
            GroupWorkerDayPermission.objects.create(
                group=self.admin_group,
                worker_day_permission=WorkerDayPermission.objects.get(
                    action=WorkerDayPermission.CREATE,
                    graph_type=graph_type,
                    wd_type=wd_type,
                )
            )
            GroupWorkerDayPermission.objects.create(
                group=self.admin_group,
                worker_day_permission=WorkerDayPermission.objects.get(
                    action=WorkerDayPermission.DELETE,
                    graph_type=graph_type,
                    wd_type=prev_wd_type,
                )
            )
        else:
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
            self.url, 'post', WorkerDayPermission.CREATE, WorkerDayPermission.PLAN, WorkerDay.TYPE_WORKDAY)
        wd = WorkerDay.objects.last()

        # update
        self._test_wd_perm(
            f"{self.url}{wd.id}/", 'put',
            WorkerDayPermission.UPDATE, WorkerDayPermission.PLAN, WorkerDay.TYPE_HOLIDAY, prev_wd_type=WorkerDay.TYPE_WORKDAY,
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_HOLIDAY)

        # delete
        self._test_wd_perm(
            f"{self.url}{wd.id}/", 'delete',
            WorkerDayPermission.DELETE,
            WorkerDayPermission.PLAN,
            wd.type,
        )

    def test_cant_create_worker_day_with_shop_mismatch(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type2.id}
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
            "employee_id": self.employee2.id,
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
        self.employee2.tabel_code = 'empl_2'
        self.employee2.save()

        data = {
          "ranges": [
            {
              "worker": self.employee2.tabel_code,
              "dt_from": self.dt - timedelta(days=10),
              "dt_to": self.dt + timedelta(days=10),
              "type": WorkerDay.TYPE_MATERNITY,
              "is_fact": True,  # проверим, что наличие is_fact True не влияет (через этот метод всегда в план)
              "is_approved": True
            }
          ]
        }
        response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.employee2.tabel_code: {'created_count': 21, 'deleted_count': 1, 'existing_count': 0}}
        )
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())
        self.assertEqual(
            WorkerDay.objects.filter(
                employee__tabel_code=self.employee2.tabel_code,
                type_id=WorkerDay.TYPE_MATERNITY,
                is_approved=True,
                is_fact=False,
            ).count(),
            21,
        )
        self.assertEqual(
            WorkerDay.objects.filter(
                employee__tabel_code=self.employee2.tabel_code,
                type_id=WorkerDay.TYPE_MATERNITY,
                is_approved=False,
                is_fact=False,
            ).count(),
            21,
        )

        response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.employee2.tabel_code: {'created_count': 0, 'deleted_count': 0, 'existing_count': 21}}
        )

        wd = WorkerDay.objects.filter(
            employee=self.employee2,
            dt=self.dt,
            is_fact=False,
            is_approved=True,
            type_id=WorkerDay.TYPE_MATERNITY,
        ).last()
        self.assertIsNotNone(wd.created_by)
        self.assertEqual(wd.created_by.id, self.user1.id)

    def test_change_range_for_workday_and_vacation_on_one_date(self):
        self.employee2.tabel_code = 'empl_2'
        self.employee2.save()

        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()
        vacation_type.allowed_additional_types.add(workday_type)

        WorkerDay.objects.all().delete()
        dt = date(2021, 6, 7)
        for is_approved in [True, False]:
            WorkerDayFactory(
                is_approved=is_approved,
                is_fact=False,
                shop=self.shop2,
                employment=self.employment2,
                employee=self.employee2,
                work_hours=timedelta(hours=10),
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
            )
            WorkerDayFactory(
                is_approved=is_approved,
                is_fact=False,
                shop=self.shop,
                employment=self.employment2,
                employee=self.employee2,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(8)),
                dttm_work_end=datetime.combine(dt, time(22)),
            )

        data = {
          "ranges": [
            {
              "worker": self.employee2.tabel_code,
              "dt_from": dt - timedelta(days=10),
              "dt_to": dt + timedelta(days=10),
              "type": WorkerDay.TYPE_VACATION,
              "is_fact": True,  # проверим, что наличие is_fact True не влияет (через этот метод всегда в план)
              "is_approved": True
            }
          ]
        }
        response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.employee2.tabel_code: {'created_count': 20, 'deleted_count': 0, 'existing_count': 1}}
        )
        self.assertEqual(
            WorkerDay.objects.filter(
                employee__tabel_code=self.employee2.tabel_code,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_approved=True,
                is_fact=False,
            ).count(),
            1,
        )
        self.assertEqual(
            WorkerDay.objects.filter(
                employee__tabel_code=self.employee2.tabel_code,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=True,
                is_fact=False,
            ).count(),
            21,
        )
        self.assertEqual(
            WorkerDay.objects.filter(
                employee__tabel_code=self.employee2.tabel_code,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_approved=False,
                is_fact=False,
            ).count(),
            1,
        )
        self.assertEqual(
            WorkerDay.objects.filter(
                employee__tabel_code=self.employee2.tabel_code,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
                is_fact=False,
            ).count(),
            21,
        )

    def test_change_range_set_work_hours_from_average_sawh_hours(self):
        self.employee2.tabel_code = 'empl_2'
        self.employee2.save()
        self.employee2.user.network.round_work_hours_alg = Network.ROUND_TO_HALF_AN_HOUR
        self.employee2.user.network.save()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()

        WorkerDay.objects.all().delete()
        dt = date(2021, 6, 7)
        data = {
          "ranges": [
            {
              "worker": self.employee2.tabel_code,
              "dt_from": dt,
              "dt_to": dt,
              "type": WorkerDay.TYPE_VACATION,
              "is_fact": False,
              "is_approved": True
            }
          ]
        }
        response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.filter(type=vacation_type).count(), 2)
        approved_vac = WorkerDay.objects.get(is_approved=True)
        self.assertEqual(approved_vac.work_hours, timedelta(seconds=19800))

    def test_change_range_fact_recalculated_on_plan_approved_delete(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            self.employee2.tabel_code = 'empl_2'
            self.employee2.save()
            self.shop.network.only_fact_hours_that_in_approved_plan = True
            self.shop.network.save()
            WorkerDay.objects.all().delete()
            dt = date(2021, 6, 7)
            for is_approved in [True, False]:
                for is_fact in [True, False]:
                    WorkerDayFactory(
                        is_approved=is_approved,
                        is_fact=is_fact,
                        shop=self.shop,
                        employment=self.employment2,
                        employee=self.employee2,
                        dt=dt,
                        type_id=WorkerDay.TYPE_WORKDAY,
                        dttm_work_start=datetime.combine(dt, time(8)),
                        dttm_work_end=datetime.combine(dt, time(22)),
                    )
            WorkerDay.set_closest_plan_approved(
                q_obj=Q(employee_id=self.employee2.id, dt=dt),
                delta_in_secs=60*60*5,
            )
            for fact_wd in WorkerDay.objects.filter(dt=dt, employee=self.employee2, is_fact=True):
                fact_wd.save()
                self.assertIsNotNone(fact_wd.closest_plan_approved_id)
                self.assertEqual(fact_wd.work_hours, timedelta(seconds=45900))

            data = {
                "ranges": [
                    {
                        "worker": self.employee2.tabel_code,
                        "dt_from": dt,
                        "dt_to": dt,
                        "type": WorkerDay.TYPE_VACATION,
                        "is_fact": False,
                        "is_approved": True
                    }
                ]
            }
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertDictEqual(
                response.json(),
                {self.employee2.tabel_code: {'created_count': 1, 'deleted_count': 1, 'existing_count': 0}}
            )
            self.assertEqual(
                WorkerDay.objects.filter(
                    employee__tabel_code=self.employee2.tabel_code,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    is_fact=False,
                ).count(),
                0,
            )
            self.assertEqual(
                WorkerDay.objects.filter(
                    employee__tabel_code=self.employee2.tabel_code,
                    type_id=WorkerDay.TYPE_VACATION,
                    is_approved=True,
                    is_fact=False,
                ).count(),
                1,
            )
            self.assertEqual(
                WorkerDay.objects.filter(
                    employee__tabel_code=self.employee2.tabel_code,
                    type_id=WorkerDay.TYPE_VACATION,
                    is_approved=False,
                    is_fact=False,
                ).count(),
                1,
            )
            self.assertEqual(
                WorkerDay.objects.filter(
                    employee__tabel_code=self.employee2.tabel_code,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    is_fact=True,
                ).count(),
                2,
            )
            for fact_wd in WorkerDay.objects.filter(dt=dt, employee=self.employee2, is_fact=True):
                self.assertIsNone(fact_wd.closest_plan_approved_id)
                self.assertEqual(fact_wd.work_hours, timedelta(seconds=0))

    def test_change_range_is_blocked(self):	
        self.employee2.tabel_code = 'empl_2'	
        self.employee2.save()	
        data = {	
          "ranges": [	
            {	
              "worker": self.employee2.tabel_code,	
              "dt_from": self.dt - timedelta(days=10),	
              "dt_to": self.dt + timedelta(days=10),	
              "type": WorkerDay.TYPE_MATERNITY,	
              "is_fact": False,	
              "is_approved": True,	
              "is_blocked": True,	
            }	
          ]	
        }	
        response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')	
        self.assertEqual(response.status_code, status.HTTP_200_OK)	
        self.assertDictEqual(	
            response.json(),	
            {self.employee2.tabel_code: {'created_count': 21, 'deleted_count': 1, 'existing_count': 0}}	
        )	
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())	
        self.assertEqual(	
            WorkerDay.objects.filter(	
                employee__tabel_code=self.employee2.tabel_code,	
                type_id=WorkerDay.TYPE_MATERNITY,	
                is_approved=True,	
                is_blocked=True,	
                is_fact=False,	
            ).count(),	
            21,	
        )	
        self.assertEqual(	
            WorkerDay.objects.filter(	
                employee__tabel_code=self.employee2.tabel_code,	
                type_id=WorkerDay.TYPE_MATERNITY,	
                is_approved=False,	
                is_blocked=True,	
                is_fact=False,	
            ).count(),	
            21,	
        )	
        response = self.client.post(self.get_url('WorkerDay-change-range'), data, format='json')	
        self.assertEqual(response.status_code, status.HTTP_200_OK)	
        self.assertDictEqual(	
            response.json(),	
            {self.employee2.tabel_code: {'created_count': 0, 'deleted_count': 0, 'existing_count': 21}}	
        )	
        wd = WorkerDay.objects.filter(	
            employee=self.employee2,	
            dt=self.dt,	
            is_fact=False,	
            is_approved=True,	
            is_blocked=True,	
            type_id=WorkerDay.TYPE_MATERNITY,	
        ).last()	
        self.assertIsNotNone(wd.created_by)	
        self.assertEqual(wd.created_by.id, self.user1.id)

    def test_cant_create_workday_if_user_has_no_active_employment(self):
        WorkerDay.objects_with_excluded.filter(employee=self.employee2).delete()
        Employment.objects.filter(employee__user=self.user2).delete()
        dt = self.dt - timedelta(days=60)
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": dt,
            "is_fact": False,
            "is_approved": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(
            resp.json(),
            {
                "detail": "Невозможно создать рабочий день, так как пользователь в этот период не трудоустроен"
            },
        )

    def test_can_create_workday_for_user_from_outsourcing_network_only_with_explicit_perms(self):
        outsource_network = Network.objects.create(
            name='outsource',
            code='outsource',
        )
        NetworkConnect.objects.create(
            client_id=self.user2.network_id,
            outsourcing=outsource_network,
        )
        WorkerDay.objects_with_excluded.filter(employee=self.employee2).delete()
        outsource_shop = Shop.objects.create(
            network=outsource_network,
            name='oursource_shop',
            region=self.region,
        )
        User.objects.filter(id=self.user2.id).update(network=outsource_network)
        Employment.objects.filter(employee__user=self.user2).update(shop=outsource_shop)
        dt = self.dt - timedelta(days=60)
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": dt,
            "is_fact": False,
            "is_approved": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 403)
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.CREATE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.OUTSOURCE_NETWORK_EMPLOYEE,
            shop_type=GroupWorkerDayPermission.MY_SHOPS,
        )
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_wd_created_as_vacancy_for_other_shop_and_employment_was_set(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee8.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertTrue(wd.is_vacancy)
        self.assertEqual(wd.employment.id, self.employment8.id)

    def test_shop_id_set_to_none_if_wd_type_is_day_off(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee8.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_HOLIDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertIsNone(wd.shop_id)
        self.assertIsNone(wd.dttm_work_start)
        self.assertIsNone(wd.dttm_work_end)

    def test_create_vacancy_for_the_same_shop_then_update_for_other_shop(self):
        data = {
            "shop_id": self.shop2.id,
            "employee_id": self.employee8.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type2.id}
            ]
        }
        resp = self.client.post(self.get_url('WorkerDay-list'), data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertFalse(wd.is_vacancy)
        self.assertEqual(wd.employment.id, self.employment8.id)

        data['shop_id'] = self.shop.id
        data['worker_day_details'][0]['work_type_id'] = self.work_type.id
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd.pk), data, format='json')
        self.assertEqual(resp.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_vacancy)

        data['shop_id'] = self.shop2.id
        data['worker_day_details'][0]['work_type_id'] = self.work_type2.id
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd.pk), data, format='json')
        self.assertEqual(resp.status_code, 200)
        wd.refresh_from_db()
        self.assertFalse(wd.is_vacancy)

    def test_inactive_employment_replaced_by_active(self):
        WorkerDay.objects.all().delete()
        Employment.objects.filter(id=self.employment2.id).update(
            dt_hired=self.dt - timedelta(days=100),
            dt_fired=self.dt - timedelta(days=1),
        )
        e2_2 = Employment.objects.create(
            code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            employee=self.employee2,
            shop=self.shop2,
            function_group=self.employee_group,
            dt_hired=self.dt,
            dt_fired=self.dt + timedelta(days=100),
        )
        data = {
            "shop_id": self.shop2.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type2.id}
            ]
        }
        resp = self.client.post(self.get_url('WorkerDay-list'), data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertEqual(wd.employment.id, e2_2.id)

    # def test_cant_create_fact_worker_day_when_there_is_no_plan_for_outsource_user(self):
    #     outsource_network = Network.objects.create(name='outsource')
    #     outsource_user = User.objects.create(
    #         username='outsource',
    #         network=outsource_network,
    #     )
    #     outsource_shop = Shop.objects.create(
    #         name='outsource',
    #         network=outsource_network,
    #         region=self.region,
    #     )
    #     outsource_employee = Employee.objects.create(
    #         user=outsource_user,
    #         tabel_code='outsource',
    #     )
    #     outsource_employment = Employment.objects.create(
    #         employee=outsource_employee,
    #         shop=outsource_shop,
    #     )
    #     data = {
    #         "shop_id": self.shop2.id,
    #         "employee_id": outsource_employee.id,
    #         "dt": self.dt,
    #         "is_fact": True,
    #         "is_approved": True,
    #         "type": WorkerDay.TYPE_WORKDAY,
    #         "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
    #         "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
    #         "worker_day_details": [{
    #             "work_part": 1.0,
    #             "work_type_id": self.work_type2.id}
    #         ]
    #     }
    #     resp = self.client.post(self.url, data, format='json')
    #     self.assertEqual(resp.status_code, 400)
    #     self.assertDictEqual(
    #         resp.json(),
    #         {
    #             "error": [
    #                 "Не существует рабочего дня в плановом подтвержденном графике. "
    #                 "Необходимо создать и подтвердить рабочий день в плановом графике, "
    #                 "или проверить, что магазины в плановом и фактическом графиках совпадают."
    #             ]
    #         },
    #     )

    def test_valid_error_message_returned_when_dt_is_none(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": None,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['dt'][0], 'Поле дата не может быть пустым.')

    def test_network_breaks(self):
        Employment.objects.all().update(position=None)
        Shop.objects.all().update(settings=None)
        dt = date.today()
        WorkerDay.objects.all().delete()
        self.employment2.refresh_from_db()
        self.shop.refresh_from_db()
        self.network.breaks = self.breaks
        self.network.save()
        wd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        self.assertEqual(wd.work_hours, timedelta(hours=10, minutes=45))

    def test_create_and_update_with_bad_dates(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(18)),
            "dttm_work_end": datetime.combine(self.dt, time(2)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': ['Дата начала должна быть меньше чем дата окончания.']})
        wd = WorkerDay.objects.get(dt=self.dt, shop=self.shop, employee_id=self.employee2.id, is_approved=False, is_fact=False)
        response = self.client.put(self.url + f'{wd.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': ['Дата начала должна быть меньше чем дата окончания.']})
        data['dt'] = self.dt + timedelta(1)
        data['dttm_work_end'] = datetime.combine(self.dt, time(22))
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': ['Дата начала должна быть меньше чем дата окончания.']})
    
    def test_create_update_delete_with_group_perms(self):
        self.admin_group.subordinates.clear()
        WorkerDay.objects.all().delete()
        wd_not_approved_to_update = WorkerDayFactory(
            shop_id=self.shop.id,
            employee_id=self.employee2.id,
            dt=self.dt,
            is_fact=False,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(11)),
            dttm_work_end=datetime.combine(self.dt, time(18)),
            cashbox_details__work_type__work_type_name__name='Работа',
        )
        wd_update_data = {
            "type": WorkerDay.TYPE_HOLIDAY,
            "employee_id": self.employee2.id,
            "dt": self.dt,
        }
        wd_not_approved_to_delete = WorkerDayFactory(
            shop_id=self.shop.id,
            employee_id=self.employee2.id,
            dt=self.dt + timedelta(1),
            is_fact=False,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(11)),
            dttm_work_end=datetime.combine(self.dt, time(19)),
            cashbox_details__work_type__work_type_name__name='Работа',
        )
        wd_not_approved_to_create = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": self.dt + timedelta(2),
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt + timedelta(2), time(11)),
            "dttm_work_end": datetime.combine(self.dt + timedelta(2), time(18)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, self.dump_data(wd_not_approved_to_create), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd_not_approved_to_update.id), self.dump_data(wd_update_data), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        resp = self.client.delete(self.get_url('WorkerDay-detail', pk=wd_not_approved_to_delete.id))
        self.assertEqual(resp.status_code, 403)
        self.admin_group.subordinates.add(self.employment2.function_group)
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop2)
        resp = self.client.post(self.url, self.dump_data(wd_not_approved_to_create), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd_not_approved_to_update.id), self.dump_data(wd_update_data), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        resp = self.client.delete(self.get_url('WorkerDay-detail', pk=wd_not_approved_to_delete.id))
        self.assertEqual(resp.status_code, 403)
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop)
        resp = self.client.post(self.url, self.dump_data(wd_not_approved_to_create), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        self.assertIsNotNone(WorkerDay.objects.filter(id=resp.json()['id']).first())
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd_not_approved_to_update.id), self.dump_data(wd_update_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        wd_not_approved_to_update.refresh_from_db()
        self.assertEqual(wd_not_approved_to_update.type_id, WorkerDay.TYPE_HOLIDAY)
        resp = self.client.delete(self.get_url('WorkerDay-detail', pk=wd_not_approved_to_delete.id))
        self.assertEqual(resp.status_code, 204)
        self.assertIsNone(WorkerDay.objects.filter(id=wd_not_approved_to_delete.id).first())
    
    def test_do_not_check_perms_if_employee_has_no_groups(self):
        self.admin_group.subordinates.clear()
        self.employment2.position = None
        self.employment2.function_group = None
        self.employment2.save()
        wd_not_approved_to_create = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": self.dt + timedelta(2),
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt + timedelta(2), time(11)),
            "dttm_work_end": datetime.combine(self.dt + timedelta(2), time(18)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, self.dump_data(wd_not_approved_to_create), content_type='application/json')
        self.assertEqual(resp.status_code, 201)

    def test_batch_create_or_update_worker_days(self):
        WorkerDay.objects.all().delete()
        options = {
            'return_response': True,
        }
        data = {
           'data':  [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(14)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(18)),
                    "dttm_work_end": datetime.combine(self.dt, time(21)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
            'options': options,
        }

        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(
            resp, 'Создание нескольких дней на одну дату для одного сотрудника запрещено.', status_code=400)

        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp_data = resp.json()
        id1 = resp_data.get('data')[0]['id']
        wd1 = WorkerDay.objects.get(id=id1)

        self.assertEqual(len(resp_data.get('data')), 2)
        wdays_qs = WorkerDay.objects.filter(
            dt=self.dt,
            shop=self.shop,
            employee_id=self.employee2.id,
            is_approved=False,
            is_fact=False,
        )
        self.assertEqual(wdays_qs.count(), 2)
        self.assertEqual(wdays_qs.filter(source=WorkerDay.SOURCE_FAST_EDITOR).count(), 2)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day__in=wdays_qs).count(), 2)
        time_module.sleep(0.1)
        resp_data.get('data').pop(1)
        resp_data['options'] = options
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(resp_data), content_type='application/json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp_data = resp.json()
        resp_data.get('data')[0]["dttm_work_start"] = datetime.combine(self.dt, time(9))
        self.assertDictEqual(resp_data['stats'], {'WorkerDay': {'deleted': 1, 'skipped': 1},
            'WorkerDayCashboxDetails': {'deleted': 1, 'skipped': 1},
            'WorkerDayOutsourceNetwork': {}})
        id2 = resp_data.get('data')[0]['id']
        self.assertEqual(len(resp_data.get('data')), 1)
        self.assertEqual(wdays_qs.count(), 1)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day__in=wdays_qs).count(), 1)
        self.assertEqual(id1, id2)
        wd2 = WorkerDay.objects.get(id=id2)
        self.assertEqual(wd1.dttm_modified, wd2.dttm_modified)  # проверка, что время не обновляется

        wd_data = resp_data.get('data').pop(0)
        # при отправке пустого списка нам нужно передать "разрез" данных
        # в рамках которого мы будем определять какие объекты нам нужно удалить
        # например: мы редактируем расписание и хотим удалить все дни на дату для сотрудника в плане черновике
        # в этом случае мы педеаем пустой список в данных и передаем "разрез" по сотруднику, дате, is_fact, is_approved
        resp_data['data'] = []
        options['delete_scope_values_list'] = [
            {
                'employee_id': wd_data['employee_id'],
                'dt': wd_data['dt'],
                'is_fact': wd_data['is_fact'],
                'is_approved': wd_data['is_approved'],
            },
        ]
        options.pop('return_response')
        resp_data['options'] = options
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(resp_data),
            content_type='application/json')
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                'stats': {
                    "WorkerDay": {
                        "deleted": 1
                    },
                    "WorkerDayCashboxDetails": {
                        "deleted": 1
                    }
                },
            }
        )

    def test_batch_create_or_update_worker_days_group_perms(self):
        self.admin_group.subordinates.clear()
        WorkerDay.objects.all().delete()
        options = {
            'return_response': True,
        }
        data = {
           'data':  [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(14)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(18)),
                    "dttm_work_end": datetime.combine(self.dt, time(21)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
            'options': options,
        }

        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {
                "detail": "У вас нет прав на создание типа дня \"Рабочий день\" для сотрудника Иванов И. в подразделении Shop1"
            }
        )

        WorkerDay.objects.create(
            **{
                "shop_id": self.shop.id,
                "employee_id": self.employee2.id,
                "employment_id": self.employment2.id,
                "dt": self.dt,
                "is_fact": False,
                "is_approved": False,
                "type_id": WorkerDay.TYPE_WORKDAY,
                "dttm_work_start": datetime.combine(self.dt, time(11)),
                "dttm_work_end": datetime.combine(self.dt, time(14)),
            },
        )

        delete_data = {
            'data': [],
            'options': {
                'delete_scope_values_list': [
                    {
                        'employee_id': self.employee2.id,
                        'dt': self.dt,
                        'is_fact': False,
                        'is_approved': False,
                    },
                ]
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {
                "detail": "У вас нет прав на удаление типа дня \"Рабочий день\" для сотрудника Иванов И. в подразделении Shop1"
            }
        )

        self.admin_group.subordinates.add(self.employment2.function_group)
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop2)
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {
                "detail": "У вас нет прав на удаление типа дня \"Рабочий день\" для сотрудника Иванов И. в подразделении Shop1"
            }
        )
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {
                "detail": "У вас нет прав на создание типа дня \"Рабочий день\" для сотрудника Иванов И. в подразделении Shop1"
            }
        )
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop)
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data),
            content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            resp.json(),
            {
                'stats': {
                    "WorkerDay": {
                        "deleted": 2
                    },
                    "WorkerDayCashboxDetails": {
                        "deleted": 2
                    }
                },
            }
        )

    def test_batch_create_or_update_worker_days_group_perms_dt(self):
        WorkerDay.objects.all().delete()
        options = {
            'return_response': True,
        }
        data = {
           'data':  [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(18)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt + timedelta(1),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt + timedelta(1), time(12)),
                    "dttm_work_end": datetime.combine(self.dt + timedelta(1), time(21)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
            'options': options,
        }

        self.employment2.dt_fired = self.dt
        self.employment2.save()
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop)
        empl2 = Employment.objects.create(
            employee=self.employee2,
            dt_hired=self.dt + timedelta(1),
            shop=self.shop2,
        )
        WorkerDay.objects.create(
            **{
                "shop_id": self.shop2.id,
                "employee_id": self.employee2.id,
                "employment_id": empl2.id,
                "dt": self.dt + timedelta(1),
                "is_fact": False,
                "is_approved": False,
                "type_id": WorkerDay.TYPE_WORKDAY,
                "dttm_work_start": datetime.combine(self.dt + timedelta(1), time(11)),
                "dttm_work_end": datetime.combine(self.dt + timedelta(1), time(14)),
            },
        )
        WorkerDay.objects.create(
            **{
                "shop_id": self.shop.id,
                "employee_id": self.employee2.id,
                "dt": self.dt,
                "employment_id": self.employment2.id,
                "is_fact": False,
                "is_approved": False,
                "type_id": WorkerDay.TYPE_WORKDAY,
                "dttm_work_start": datetime.combine(self.dt, time(11)),
                "dttm_work_end": datetime.combine(self.dt, time(14)),
            },
        )

        delete_data = {
            'data': [],
            'options': {
                'delete_scope_values_list': [
                    {
                        'employee_id': self.employee2.id,
                        'dt': self.dt + timedelta(1),
                        'is_fact': False,
                        'is_approved': False,
                    },
                ]
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {
                "detail": f"У вас нет прав на удаление типа дня \"Рабочий день\" для сотрудника {self.user2.short_fio} в подразделении Shop2"
            }
        )
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {
                "detail": f"У вас нет прав на создание типа дня \"Рабочий день\" для сотрудника {self.user2.short_fio} в подразделении Shop1"
            }
        )
        self.assertEqual(WorkerDay.objects.count(), 2)
        delete_data['options']['delete_scope_values_list'][0]['dt'] = self.dt
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data),
            content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            resp.json(),
            {
                'stats': {
                    "WorkerDay": {
                        "deleted": 1
                    },
                },
            }
        )
        data['data'].pop(1)
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_work_hours_recalculated_on_batch_update(self):
        WorkerDay.objects.all().delete()
        options = {
            'return_response': True,
        }
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(10)),
                    "dttm_work_end": datetime.combine(self.dt, time(16)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
            'options': options,
        }

        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp_data = resp.json()
        wd_id = resp_data['data'][0]['id']
        wd = WorkerDay.objects.get(id=wd_id)
        self.assertEqual(wd.work_hours, timedelta(seconds=5.5*60*60))
        data['data'][0] = resp_data['data'][0]
        data['data'][0]['dttm_work_end'] = datetime.combine(self.dt, time(20))
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        wd.refresh_from_db()
        self.assertEqual(wd.work_hours, timedelta(seconds=8.75*60*60))

    def test_cant_batch_create_different_wday_types_on_one_date_for_one_employee(self):
        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(14)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_HOLIDAY,
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(
            resp, 'Операция не может быть выполнена. '
                  'Нарушены ограничения по разрешенным типам дней на одну дату для одного сотрудника.', status_code=400)

    def test_cant_batch_create_different_dayoff_types_on_one_date_for_one_employee(self):
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_VACATION,
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_HOLIDAY,
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(
            resp, 'Операция не может быть выполнена. '
                  'Нарушены ограничения по разрешенным типам дней на одну дату для одного сотрудника.', status_code=400)

    def test_cant_create_multiple_wdays_on_one_date_if_setting_is_enabled(self):
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(17)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(19)),
                    "dttm_work_end": datetime.combine(self.dt, time(22)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(
            resp, 'Создание нескольких дней на одну дату для одного сотрудника запрещено.', status_code=400)

    def test_batch_create_or_update_workerdays_user_work_time_overlap_validation(self):
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(17)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(15)),
                    "dttm_work_end": datetime.combine(self.dt, time(22)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(
            resp, 'Операция не может быть выполнена. Недопустимое пересечение времени работы.', status_code=400)

    def test_batch_create_or_update_wd_perms(self):
        GroupWorkerDayPermission.objects.all().delete()
        WorkerDay.objects.all().delete()
        wd_data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(11)),
            "dttm_work_end": datetime.combine(self.dt, time(15)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        data = {
            'data': [
                wd_data,
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(
            resp, 'У вас нет прав на создание типа дня', status_code=403)

        create_plan_workday_perm = WorkerDayPermission.objects.get(
            action=WorkerDayPermission.CREATE,
            graph_type=WorkerDayPermission.PLAN,
            wd_type_id=WorkerDay.TYPE_WORKDAY,
        )
        gwdp_create = GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=create_plan_workday_perm,
            limit_days_in_past=1,
            limit_days_in_future=1,
        )
        update_plan_workday_perm = WorkerDayPermission.objects.get(
            action=WorkerDayPermission.UPDATE,
            graph_type=WorkerDayPermission.PLAN,
            wd_type_id=WorkerDay.TYPE_WORKDAY,
        )
        gwdp_update = GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=update_plan_workday_perm,
            limit_days_in_past=1,
            limit_days_in_future=1,
        )

        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WorkerDay.objects.count(), 1)

        wd_data['dt'] = self.dt - timedelta(days=2)
        wd_data['dttm_work_start'] = datetime.combine(self.dt - timedelta(days=2), time(11))
        wd_data['dttm_work_end'] = datetime.combine(self.dt - timedelta(days=2), time(15))
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(resp, 'Необходимо изменить даты', status_code=403)

        wd_data['dt'] = self.dt + timedelta(days=2)
        wd_data['dttm_work_start'] = datetime.combine(self.dt + timedelta(days=2), time(11))
        wd_data['dttm_work_end'] = datetime.combine(self.dt + timedelta(days=2), time(15))
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(resp, 'Необходимо изменить даты', status_code=403)

        gwdp_create.limit_days_in_past = None
        gwdp_create.limit_days_in_future = None
        gwdp_update.limit_days_in_past = None
        gwdp_update.limit_days_in_future = None
        gwdp_create.save()
        gwdp_update.save()

        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WorkerDay.objects.count(), 2)

        # попытка удалить день
        data['data'] = []
        options = {'delete_scope_values_list': [
            {
                'employee_id': wd_data['employee_id'],
                'dt': wd_data['dt'],
                'is_fact': wd_data['is_fact'],
                'is_approved': wd_data['is_approved'],
            },
        ]}
        data['options'] = options
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(resp, 'У вас нет прав на удаление типа дня', status_code=403)

        delete_plan_workday_perm = WorkerDayPermission.objects.get(
            action=WorkerDayPermission.DELETE,
            graph_type=WorkerDayPermission.PLAN,
            wd_type_id=WorkerDay.TYPE_WORKDAY,
        )
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=delete_plan_workday_perm,
        )

        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WorkerDay.objects.count(), 1)

    def test_fact_work_hours_calculated_on_batch_create_workerdays(self):
        self.network.only_fact_hours_that_in_approved_plan = False
        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": True,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(10)),
                    "dttm_work_end": datetime.combine(self.dt, time(14)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": True,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(16)),
                    "dttm_work_end": datetime.combine(self.dt, time(23)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        fact_not_approved_qs = WorkerDay.objects.filter(is_fact=True, is_approved=False)
        self.assertEqual(fact_not_approved_qs.count(), 2)
        fact_not_approved_wdays = list(fact_not_approved_qs.order_by('dttm_work_start'))
        self.assertEqual(fact_not_approved_wdays[0].work_hours, timedelta(seconds=3.5*60*60))
        self.assertEqual(fact_not_approved_wdays[1].work_hours, timedelta(seconds=6*60*60))

    def test_fact_work_hours_recalculated_after_adding_and_approving_closest_plan(self):
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": True,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(10)),
                    "dttm_work_end": datetime.combine(self.dt, time(14)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": True,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(16)),
                    "dttm_work_end": datetime.combine(self.dt, time(23)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        fact_not_approved_qs = WorkerDay.objects.filter(is_fact=True, is_approved=False)
        self.assertEqual(fact_not_approved_qs.count(), 2)
        fact_not_approved_wdays = list(fact_not_approved_qs.order_by('dttm_work_start'))
        self.assertEqual(fact_not_approved_wdays[0].work_hours, timedelta(seconds=0))
        self.assertEqual(fact_not_approved_wdays[1].work_hours, timedelta(seconds=0))

        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(10)),
                    "dttm_work_end": datetime.combine(self.dt, time(14)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(16)),
                    "dttm_work_end": datetime.combine(self.dt, time(23)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved_qs = WorkerDay.objects.filter(is_fact=False, is_approved=False)
        self.assertEqual(plan_not_approved_qs.count(), 2)

        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.dt,
            dt_to=self.dt,
            wd_types=[WorkerDay.TYPE_WORKDAY],
        )
        self.assertEqual(resp.status_code, 200)
        plan_approved_qs = WorkerDay.objects.filter(is_fact=False, is_approved=True)
        self.assertEqual(plan_approved_qs.count(), 2)

        fact_not_approved_wdays[0].refresh_from_db()
        self.assertIsNotNone(fact_not_approved_wdays[0].closest_plan_approved_id)
        fact_not_approved_wdays[1].refresh_from_db()
        self.assertIsNotNone(fact_not_approved_wdays[1].closest_plan_approved_id)
        self.assertEqual(fact_not_approved_wdays[0].work_hours, timedelta(seconds=3.5*60*60))
        self.assertEqual(fact_not_approved_wdays[1].work_hours, timedelta(seconds=6*60*60))

    def test_batch_work_hours_dayoff_hours_calculated_as_average_sawh_hours(self):
        WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS,
        )

        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": date(2021, 11, 2),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_VACATION,
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved_qs = WorkerDay.objects.filter(is_fact=False, is_approved=False)
        self.assertEqual(plan_not_approved_qs.count(), 1)
        plan_not_approved_wday = plan_not_approved_qs.first()
        self.assertEqual(plan_not_approved_wday.work_hours, timedelta(seconds=19080))

    def test_batch_work_hours_dayoff_hours_calculated_as_norm_hours(self):
        WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_NORM_HOURS,
        )

        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": date(2021, 11, 2),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_VACATION,
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved_qs = WorkerDay.objects.filter(is_fact=False, is_approved=False)
        self.assertEqual(plan_not_approved_qs.count(), 1)
        plan_not_approved_wday = plan_not_approved_qs.first()
        self.assertEqual(plan_not_approved_wday.work_hours, timedelta(seconds=60*60*8))

    def test_batch_work_hours_dayoff_work_hours_method_manual(self):
        WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_SICK,
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL,
        )

        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": date(2021, 11, 2),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_SICK,
                    "work_hours": "10:30:00",
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved_qs = WorkerDay.objects.filter(is_fact=False, is_approved=False)
        self.assertEqual(plan_not_approved_qs.count(), 1)
        plan_not_approved_wday = plan_not_approved_qs.first()
        self.assertEqual(plan_not_approved_wday.work_hours, timedelta(seconds=60*60*10.5))
    
    def test_batch_work_hours_dayoff_work_hours_method_manual_or_calculated_as_average_sawh_hours(self):
        WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL_OR_MONTH_AVERAGE_SAWH_HOURS,
        )

        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": date(2021, 11, 2),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_VACATION,
                    "work_hours": "10:30:00",
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": date(2021, 11, 3),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_VACATION,
                    "work_hours": None,
                },
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": date(2021, 11, 4),
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_VACATION,
                    "work_hours": "00:00:00",
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved_qs = WorkerDay.objects.filter(is_fact=False, is_approved=False)
        self.assertEqual(plan_not_approved_qs.count(), 3)
        plan_not_approved_wday_manual = plan_not_approved_qs.get(dt=date(2021, 11, 2))
        plan_not_approved_wday_calculated_as_average_sawh_hours = plan_not_approved_qs.get(dt=date(2021, 11, 3))
        plan_not_approved_wday_manual_zero = plan_not_approved_qs.get(dt=date(2021, 11, 4))
        self.assertEqual(plan_not_approved_wday_manual.work_hours, timedelta(seconds=60*60*10.5))
        self.assertEqual(plan_not_approved_wday_calculated_as_average_sawh_hours.work_hours, timedelta(seconds=19080))
        self.assertEqual(plan_not_approved_wday_manual_zero.work_hours, timedelta(0))

    def test_set_cost_per_hour(self):
        response = self.client.put(
            f'{self.url}{self.worker_day_plan_not_approved.id}/',
            data=self.dump_data(
                {
                    'cost_per_hour': 120.45,
                    'shop_id': self.shop.id,
                    'employee_id': self.employee2.id,
                    'employment_id': self.employment2.id,
                    'is_fact': False,
                    'is_approved': False,
                    'is_blocked': False,
                    'type': WorkerDay.TYPE_WORKDAY,
                    'parent_worker_day_id': self.worker_day_plan_approved.id,
                    'comment': None,
                    'dt': Converter.convert_date(self.dt),
                    'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
                    'dttm_work_start_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
                    'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
                    'dttm_work_end_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
                    'worker_day_details': [
                        {
                            'work_type_id': self.work_type.id,
                            'work_part': 1.0,
                        }
                    ],
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.worker_day_plan_not_approved.id,
            'code': None,
            'shop_id': self.shop.id,
            'employee_id': self.employee2.id,
            'employment_id': self.employment2.id,
            'is_fact': False,
            'is_approved': False,
            'is_blocked': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'parent_worker_day_id': self.worker_day_plan_approved.id,
            'comment': None,
            'dt': Converter.convert_date(self.dt),
            'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_start_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'dttm_work_end_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'work_hours': '10:45:00',
            'is_outsource': False,
            'outsources': [],
            'is_vacancy': False,
            'unaccounted_overtime': 0.0,
            'crop_work_hours_by_shop_schedule': True,
            'closest_plan_approved_id': None,
            'cost_per_hour': '120.45',
            'total_cost': 1294.8375,
        }
        response_data = response.json()
        response_data.pop('worker_day_details', None)
        self.assertEqual(response.json(), data)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertEqual(self.worker_day_plan_not_approved.cost_per_hour, Decimal("120.45"))

    def test_cost_per_hour_in_list(self):
        self.worker_day_plan_not_approved.cost_per_hour = 120.45
        self.worker_day_plan_not_approved.save()
        response = self.client.get(self.url)
        worker_day_plan_not_approved = list(filter(lambda x: x['id'] == self.worker_day_plan_not_approved.id, response.json()))[0]
        self.assertEqual(worker_day_plan_not_approved['cost_per_hour'], '120.45')
        self.assertEqual(worker_day_plan_not_approved['total_cost'], 1294.8375)

    def test_set_cost_per_hour_empty_string(self):
        response = self.client.put(
            f'{self.url}{self.worker_day_plan_not_approved.id}/',
            data=self.dump_data(
                {
                    'cost_per_hour': None,
                    'shop_id': self.shop.id,
                    'employee_id': self.employee2.id,
                    'employment_id': self.employment2.id,
                    'is_fact': False,
                    'is_approved': False,
                    'is_blocked': False,
                    'type': WorkerDay.TYPE_WORKDAY,
                    'parent_worker_day_id': self.worker_day_plan_approved.id,
                    'comment': None,
                    'dt': Converter.convert_date(self.dt),
                    'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
                    'dttm_work_start_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
                    'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
                    'dttm_work_end_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
                    'worker_day_details': [
                        {
                            'work_type_id': self.work_type.id,
                            'work_part': 1.0,
                        }
                    ],
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.worker_day_plan_not_approved.id,
            'code': None,
            'shop_id': self.shop.id,
            'employee_id': self.employee2.id,
            'employment_id': self.employment2.id,
            'is_fact': False,
            'is_approved': False,
            'is_blocked': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'parent_worker_day_id': self.worker_day_plan_approved.id,
            'comment': None,
            'dt': Converter.convert_date(self.dt),
            'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_start_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'dttm_work_end_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'work_hours': '10:45:00',
            'is_outsource': False,
            'outsources': [],
            'is_vacancy': False,
            'unaccounted_overtime': 0.0,
            'crop_work_hours_by_shop_schedule': True,
            'closest_plan_approved_id': None,
            'cost_per_hour': None,
            'total_cost': None,
        }
        response_data = response.json()
        response_data.pop('worker_day_details', None)
        self.assertEqual(response.json(), data)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertEqual(self.worker_day_plan_not_approved.cost_per_hour, None)

    def test_worker_day_details_deleted_on_wd_type_change_from_workday_to_nonworkday(self):
        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(16)),
                    "dttm_work_end": datetime.combine(self.dt, time(23)),
                    "worker_day_details": [
                        {
                            "work_part": 1.0,
                            "work_type_id": self.work_type.id
                        }
                    ]
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved = WorkerDay.objects.filter(is_fact=False, is_approved=False).first()
        data = {
            'data': [
                {
                    "id": plan_not_approved.id,
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_HOLIDAY,
                },
            ],
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        plan_not_approved.refresh_from_db()
        self.assertEqual(plan_not_approved.type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertIsNone(plan_not_approved.dttm_work_start)
        self.assertIsNone(plan_not_approved.dttm_work_end)
        self.assertEqual(plan_not_approved.worker_day_details.count(), 0)

    def _test_overlap(self, tm_work_start_first, tm_work_end_first, tm_work_start_second, tm_work_end_second, error_raised=True):
        dt = date.today()
        WorkerDay.objects.all().delete()
        wd_data = {
            'employee': self.employee2,
            'employment': self.employment2,
            'dt': dt,
            'type_id': WorkerDay.TYPE_WORKDAY,
            'shop': self.shop,
            'is_fact': False,
            'is_approved': False,
            'dttm_work_start': datetime.combine(dt, tm_work_start_first) if tm_work_start_first else None,
            'dttm_work_end': datetime.combine(dt, tm_work_end_first) if tm_work_end_first else None,
        }
        WorkerDay.objects.create(**wd_data)
        wd_data.update(
            {
                'dttm_work_start': datetime.combine(dt, tm_work_start_second) if tm_work_start_second else None,
                'dttm_work_end': datetime.combine(dt, tm_work_end_second) if tm_work_end_second else None,
            }
        )
        WorkerDay.objects.create(**wd_data)
        has_overlap = False
        try:
            WorkerDay.check_work_time_overlap(employee_id=self.employee2.id, is_fact=False, is_approved=False)
        except WorkTimeOverlap:
            has_overlap = True

        self.assertEqual(has_overlap, error_raised)

    def test_overlap(self):
        
        # start1 | start2 | end1 | end2
        self._test_overlap(time(8), time(20), time(14), time(22))

        # start2 | start1 | end2 | end1
        self._test_overlap(time(8), time(20), time(5), time(15))

        # start1 | start2 | end1 | None
        self._test_overlap(time(8), time(20), time(14), None)

        # start2 | start1 | end2 | None
        self._test_overlap(time(8), None, time(5), time(15))

        # None | start2 | end1 | end2
        self._test_overlap(None, time(20), time(14), time(22))

        # None | start1 | end2 | end1
        self._test_overlap(time(8), time(20), None, time(15))

        # start1 | start2 | end2 | end1
        self._test_overlap(time(8), time(20), time(10), time(15))

        # start2 | start1 | end1 | end2
        self._test_overlap(time(10), time(15), time(8), time(20))

        # start1 | start2 | end2 | None
        self._test_overlap(time(8), None, time(10), time(20))

        # start1==start2 | end2 | None
        self._test_overlap(time(8), None, time(8), time(20))

        # None | start2 | end2 | end1
        self._test_overlap(None, time(21), time(8), time(20))

        # None | start2 | end2==end1
        self._test_overlap(None, time(21), time(8), time(21))

        # start1 | end1 | start2 | end2
        self._test_overlap(time(10), time(15), time(16), time(20), False)

        # start1 | end1==start2 | end2
        self._test_overlap(time(10), time(15), time(15), time(20), False)

        # start1 | end1 | start2 | None
        self._test_overlap(time(10), time(15), time(15), None, False)

        # None | end1 | start2 | end2
        self._test_overlap(None, time(15), time(15), time(20), False)

    def test_batch_skip_worker_day_if_changed_only_created_by_last_edited_by_or_source(self):
        WorkerDay.objects.all().delete()
        data = {
            'data': [
                {
                    "shop_id": self.shop.id,
                    "employee_id": self.employee2.id,
                    "dt": self.dt,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt, time(11)),
                    "dttm_work_end": datetime.combine(self.dt, time(20)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
            'options': {
                'return_response': True,
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "WorkerDayCashboxDetails": {
                        "created": 1
                    },
                    "WorkerDayOutsourceNetwork": {},
                    "WorkerDay": {
                        "created": 1
                    }
                },
                "data": mock.ANY
            }
        )
        wd = WorkerDay.objects.first()
        wd.created_by = self.user2
        wd.last_edited_by = self.user2
        wd.source = wd.source + 1
        wd.save()
        data['data'] = resp_data['data']
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "WorkerDayCashboxDetails": {
                        "skipped": 1
                    },
                    "WorkerDayOutsourceNetwork": {},
                    "WorkerDay": {
                        "skipped": 1
                    }
                },
                "data": mock.ANY
            }
        )

    def test_batch_update_or_create_vacancies_by_code(self):
        WorkerDay.objects.all().delete()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()

        doc_id = uuid.uuid4()
        employee_id = uuid.uuid4()

        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            shop=None,
            dt=self.dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_approved=False,
            is_fact=False,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            shop=None,
            dt=self.dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_approved=True,
            is_fact=False,
        )

        code = f'{doc_id}:{employee_id}:{self.dt}'
        data = {
            'data': [
                {
                    "code": code,
                    "tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt": self.dt,
                    "type": WorkerDay.TYPE_VACATION,
                }
            ],
            'options': {
                "update_key_field": "code",
                "delete_scope_fields_list": [],
                "delete_scope_filters": {
                    "employee__tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt__lte": self.dt + timedelta(days=30),
                    "dt__gte": self.dt - timedelta(days=30),
                    "type_id__in": [WorkerDay.TYPE_VACATION],
                },
                "model_options": {
                    "delete_not_allowed_additional_types": True,
                    "approve_delete_scope_filters_wdays": True,
                },
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                "stats": {
                    "WorkerDayCashboxDetails": {},
                    "WorkerDayOutsourceNetwork": {},
                    "WorkerDay": {
                        "created": 1,
                        "deleted": 1
                    }
                }
            }
        )
        self.assertEqual(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_VACATION).count(), 2)
        self.assertEqual(WorkerDay.objects.exclude(type_id=WorkerDay.TYPE_VACATION).count(), 0)
        wd = WorkerDay.objects.filter(dt=self.dt, is_approved=True).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_VACATION)
        self.assertEqual(wd.code, code)

        # move vacation
        dt = self.dt + timedelta(days=1)
        data['data'][0]['dt'] = dt
        code = f'{doc_id}:{employee_id}:{dt}'
        data['data'][0]['code'] = code
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                "stats": {
                    "WorkerDayCashboxDetails": {},
                    "WorkerDayOutsourceNetwork": {},
                    "WorkerDay": {
                        "created": 1,
                        "deleted": 1
                    }
                }
            }
        )
        self.assertEqual(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_VACATION).count(), 2)
        self.assertEqual(WorkerDay.objects.exclude(type_id=WorkerDay.TYPE_VACATION).count(), 0)
        wd = WorkerDay.objects.filter(dt=self.dt, is_approved=True).first()
        self.assertIsNone(wd)
        wd = WorkerDay.objects.filter(dt=dt, is_approved=True).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_VACATION)
        self.assertEqual(wd.code, code)

    def test_sync_vacation_and_sick_at_the_same_time(self):
        WorkerDay.objects.all().delete()
        doc_id = uuid.uuid4()
        employee_id = uuid.uuid4()

        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            shop=None,
            dt=self.dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_approved=False,
            is_fact=False,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            shop=None,
            dt=self.dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_approved=True,
            is_fact=False,
        )

        code = f'{doc_id}:{employee_id}:{self.dt}'
        code2 = f'{doc_id}:{employee_id}:{self.dt + timedelta(days=1)}'
        data = {
            'data': [
                {
                    "code": code,
                    "tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt": self.dt,
                    "type": WorkerDay.TYPE_VACATION,
                },
                {
                    "code": code2,
                    "tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt": self.dt + timedelta(days=1),
                    "type": WorkerDay.TYPE_SICK,
                }
            ],
            'options': {
                "update_key_field": "code",
                "delete_scope_fields_list": [],
                "delete_scope_filters": {
                    "employee__tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt__lte": self.dt + timedelta(days=30),
                    "dt__gte": self.dt - timedelta(days=30),
                    "type_id__in": [WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK],
                },
                "model_options": {
                    "delete_not_allowed_additional_types": True,
                    "approve_delete_scope_filters_wdays": True,
                },
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                "stats": {
                    "WorkerDayCashboxDetails": {},
                    "WorkerDayOutsourceNetwork": {},
                    "WorkerDay": {
                        "created": 2,
                        "deleted": 1
                    }
                }
            }
        )
        self.assertEqual(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_VACATION).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_SICK).count(), 2)
        self.assertEqual(WorkerDay.objects.exclude(
            type_id__in=[WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK]).count(), 0)
        wd = WorkerDay.objects.filter(dt=self.dt, is_approved=True).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_VACATION)
        self.assertEqual(wd.code, code)
        wd = WorkerDay.objects.filter(dt=self.dt + timedelta(days=1), is_approved=True).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_SICK)
        self.assertEqual(wd.code, code2)

    def test_sync_vacation_when_draft_allowed_additional_type_exists(self):
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.allowed_additional_types.add(workday_type)

        WorkerDay.objects.all().delete()
        doc_id = uuid.uuid4()
        employee_id = uuid.uuid4()

        wd_draft = WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop2,
            dt=self.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            is_fact=False,
        )

        code = f'{doc_id}:{employee_id}:{self.dt}'
        data = {
            'data': [
                {
                    "code": code,
                    "tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt": self.dt,
                    "type": WorkerDay.TYPE_VACATION,
                }
            ],
            'options': {
                "update_key_field": "code",
                "delete_scope_fields_list": [],
                "delete_scope_filters": {
                    "employee__tabel_code": self.employee2.tabel_code,
                    "is_fact": False,
                    "is_approved": False,
                    "dt__lte": self.dt + timedelta(days=30),
                    "dt__gte": self.dt - timedelta(days=30),
                    "type_id__in": [WorkerDay.TYPE_VACATION],
                },
                "model_options": {
                    "delete_not_allowed_additional_types": True,
                    "approve_delete_scope_filters_wdays": True,
                },
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                "stats": {
                    "WorkerDayCashboxDetails": {},
                    "WorkerDayOutsourceNetwork": {},
                    "WorkerDay": {
                        "created": 1,
                    }
                }
            }
        )
        self.assertEqual(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_VACATION).count(), 2)
        self.assertEqual(WorkerDay.objects.exclude(
            type_id__in=[WorkerDay.TYPE_VACATION]).count(), 1)
        self.assertTrue(WorkerDay.objects.filter(id=wd_draft.id).exists())

        data['data'] = []
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                "stats": {
                    "WorkerDay": {
                        "deleted": 1,
                    }
                }
            }
        )
        self.assertEqual(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_VACATION).count(), 0)
        self.assertEqual(WorkerDay.objects.exclude(
            type_id__in=[WorkerDay.TYPE_VACATION]).count(), 1)
        self.assertTrue(WorkerDay.objects.filter(id=wd_draft.id).exists())
