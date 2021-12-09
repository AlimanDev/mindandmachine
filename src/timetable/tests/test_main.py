from decimal import Decimal
import json
import time as time_module
import uuid
from datetime import timedelta, time, datetime, date
from unittest import mock

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.db import transaction, IntegrityError
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import (
    Break,
    Network,
    Employment,
    Region,
    ShopSchedule,
    Shop,
    Employee,
    User,
    WorkerPosition,
    NetworkConnect,
)
from src.events.models import EventType
from src.notifications.models.event_notification import EventEmailNotification
from src.timetable.events import VACANCY_CONFIRMED_TYPE
from src.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
    EmploymentWorkType,
    WorkerDayType,
)
from src.timetable.tests.factories import WorkerDayFactory, WorkerDayTypeFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


class TestWorkerDay(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    maxDiff = None

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = (now() + timedelta(hours=3)).date()

        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)
        self.work_type2 = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop2)

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            parent_worker_day=self.worker_day_plan_approved
        )
        self.worker_day_fact_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30, 0)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
            closest_plan_approved=self.worker_day_plan_approved,
            last_edited_by=self.user1,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            parent_worker_day=self.worker_day_fact_approved,
            closest_plan_approved=self.worker_day_plan_approved,
            last_edited_by=self.user1,
        )

        self.client.force_authenticate(user=self.user1)
        self.network.allowed_interval_for_late_arrival = timedelta(minutes=15)
        self.network.allowed_interval_for_early_departure = timedelta(minutes=15)
        self.network.crop_work_hours_by_shop_schedule = False
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()

        self.shop.tm_open_dict = f'{{"all":"00:00:00"}}'
        self.shop.tm_close_dict = f'{{"all":"00:00:00"}}'
        self.shop.save()

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
        self.assertEquals(WorkerDay.objects.filter(is_fact=True, is_approved=True, source=WorkerDay.SOURCE_AUTO_FACT).count(), 3)
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

        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)

        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dt, today)

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
                         {'error': ['Нельзя менять подтвержденную версию.']}
                         )

        response = self.client.put(f"{self.url}{self.worker_day_fact_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': ['Нельзя менять подтвержденную версию.']})

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

    def _test_wd_perm(self, url, method, action, graph_type=None, wd_type=None):
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
        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
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

        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
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
        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
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
        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.filter(type=vacation_type).count(), 2)
        approved_vac = WorkerDay.objects.get(is_approved=True)
        self.assertEqual(approved_vac.work_hours, timedelta(seconds=19800))

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
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.json()["non_field_errors"][0],
            'Невозможно создать рабочий день, так как пользователь в этот период не трудоустроен',
        )

    def test_can_create_workday_for_user_from_outsourcing_network(self):
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

    # def test_cant_create_fact_worker_day_when_there_is_no_plan(self):
    #     data = {
    #         "shop_id": self.shop2.id,
    #         "worker_id": self.user8.id,
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
        self.assertEquals(wdays_qs.filter(source=WorkerDay.SOURCE_FAST_EDITOR).count(), 2)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day__in=wdays_qs).count(), 2)
        time_module.sleep(0.1)
        resp_data.get('data').pop(1)
        resp_data['options'] = options
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(resp_data), content_type='application/json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp_data = resp.json()
        resp_data.get('data')[0]["dttm_work_start"] = datetime.combine(self.dt, time(9))
        id2 = resp_data.get('data')[0]['id']
        self.assertEqual(len(resp_data.get('data')), 1)
        self.assertEqual(wdays_qs.count(), 1)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day__in=wdays_qs).count(), 1)
        self.assertEqual(id1, id2)
        wd2 = WorkerDay.objects.get(id=id2)
        self.assertNotEqual(wd1.dttm_modified, wd2.dttm_modified)  # проверка, что время обновляется

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
                  'Нарушены ограничения по разрешенным типам дней на одну дату для одного сотрудника..', status_code=400)

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
                  'Нарушены ограничения по разрешенным типам дней на одну дату для одного сотрудника..', status_code=400)

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
            resp, 'У вас нет прав на создание/изменение типа дня', status_code=403)

        create_or_update_plan_workday_perm = WorkerDayPermission.objects.get(
            action=WorkerDayPermission.CREATE_OR_UPDATE,
            graph_type=WorkerDayPermission.PLAN,
            wd_type_id=WorkerDay.TYPE_WORKDAY,
        )
        gwdp = GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=create_or_update_plan_workday_perm,
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
        self.assertContains(resp, 'Необходимо изменить интервал для подтверждения', status_code=403)

        wd_data['dt'] = self.dt + timedelta(days=2)
        wd_data['dttm_work_start'] = datetime.combine(self.dt + timedelta(days=2), time(11))
        wd_data['dttm_work_end'] = datetime.combine(self.dt + timedelta(days=2), time(15))
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(resp, 'Необходимо изменить интервал для подтверждения', status_code=403)

        gwdp.limit_days_in_past = None
        gwdp.limit_days_in_future = None
        gwdp.save()

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
        self.assertEquals(response.json(), data)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertEquals(self.worker_day_plan_not_approved.cost_per_hour, Decimal("120.45"))

    def test_cost_per_hour_in_list(self):
        self.worker_day_plan_not_approved.cost_per_hour = 120.45
        self.worker_day_plan_not_approved.save()
        response = self.client.get(self.url)
        worker_day_plan_not_approved = list(filter(lambda x: x['id'] == self.worker_day_plan_not_approved.id, response.json()))[0]
        self.assertEquals(worker_day_plan_not_approved['cost_per_hour'], '120.45')
        self.assertEquals(worker_day_plan_not_approved['total_cost'], 1294.8375)

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
        self.assertEquals(response.json(), data)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertEquals(self.worker_day_plan_not_approved.cost_per_hour, None)


class TestCropSchedule(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dt_now = datetime.now().date()
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(work_type_name=cls.work_type_name, shop=cls.shop)

        # всегда 1 ч перерыв, чтобы было легче считать
        cls.shop.network.crop_work_hours_by_shop_schedule = True
        cls.shop.network.only_fact_hours_that_in_approved_plan = False
        cls.shop.network.save()
        cls.shop.settings.breaks.value = '[[0, 2000, [30, 30]]]'
        cls.shop.settings.breaks.save()

    def _test_crop_hours(
            self, shop_open_h, shop_close_h, work_start_h, work_end_h, expected_work_h, bulk=False, crop=True):
        self.shop.tm_open_dict = f'{{"all":"{shop_open_h}:00:00"}}' if isinstance(shop_open_h, int) else shop_open_h
        self.shop.tm_close_dict = f'{{"all":"{shop_close_h}:00:00"}}' if isinstance(shop_close_h, int) else shop_close_h
        self.shop.save()

        WorkerDay.objects.filter(
            dt=self.dt_now,
            employee=self.employee2,
            is_fact=True,
            is_approved=True,
        ).delete()

        wd_kwargs = dict(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt_now,
            is_fact=True,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now, time(work_start_h, 00, 0)) \
                if isinstance(work_start_h, int) else work_start_h,
            dttm_work_end=datetime.combine(self.dt_now, time(work_end_h, 00, 0))
                if isinstance(work_end_h, int) else work_end_h,
            crop_work_hours_by_shop_schedule=crop,
        )
        if bulk:
            wd_kwargs['need_count_wh'] = True
        wd = WorkerDay(**wd_kwargs)
        if bulk:
            wd = WorkerDay.objects.bulk_create([wd])[0]
        else:
            wd.save()
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
            work_part=1,
        )
        self.assertEqual(
            timedelta(hours=expected_work_h) if isinstance(expected_work_h, int) else expected_work_h,
            wd.work_hours
        )

    def _test_crop_both_bulk_and_original_save(self, *args, **kwargs):
        self._test_crop_hours(*args, bulk=False, **kwargs)
        self._test_crop_hours(*args, bulk=True, **kwargs)

    def test_crop_work_hours_by_shop_schedule(self):
        # параметры: час откр. магазина, час закр. магазина, час начала работы, час конца работы, ожидаемое к-во часов
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 9)
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 12, crop=False)
        self._test_crop_both_bulk_and_original_save(10, 20, 11, 19, 7)
        self._test_crop_both_bulk_and_original_save(10, 20, 11, 19, 7, crop=False)
        self._test_crop_both_bulk_and_original_save(10, 22, 10, 23, 11)
        self._test_crop_both_bulk_and_original_save(10, 22, 10, 23, 12, crop=False)
        self._test_crop_both_bulk_and_original_save(
            10, 23, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 2)
        self._test_crop_both_bulk_and_original_save(
            10, 23, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 6, crop=False)

        # круглосуточный магазин или расписание не заполнено
        self._test_crop_both_bulk_and_original_save(
            0, 0, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 6)

        # проверка по дням недели
        weekday = self.dt_now.weekday()
        self._test_crop_both_bulk_and_original_save(
            f'{{"{weekday}":"12:00:00"}}', f'{{"{weekday}":"23:00:00"}}', 10, 20, 7)

        # факт. время работы с минутами
        self._test_crop_both_bulk_and_original_save(
            10, 22,
            datetime.combine(self.dt_now, time(9, 46, 15)),
            datetime.combine(self.dt_now, time(21, 47, 23)),
            timedelta(seconds=38843),
        )
        self._test_crop_both_bulk_and_original_save(
            10, 22,
            datetime.combine(self.dt_now, time(9, 46, 15)),
            datetime.combine(self.dt_now, time(21, 47, 23)),
            timedelta(seconds=39668),
            crop=False,
        )

        # todo: ночные смены (когда-нибудь)

    def test_zero_hours_for_holiday(self):
        ShopSchedule.objects.update_or_create(
            dt=self.dt_now,
            shop=self.shop,
            defaults=dict(
                type='H',
                opens=None,
                closes=None,
                modified_by=self.user1,
            ),
        )
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 0)


class TestWorkerDayCreateFact(TestsHelperMixin, APITestCase):
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
            "employee_id": self.employee2.id,
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

    def test_closest_plan_approved_set_on_fact_creation(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
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

        resp = self.client.post(self.url, self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        fact_id = resp.json()['id']
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.closest_plan_approved_id, plan_approved.id)

    def test_closest_plan_approved_set_on_fact_creation_when_single_plan_far_from_fact(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(12, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        resp = self.client.post(self.url, self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        fact_id = resp.json()['id']
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.closest_plan_approved_id, plan_approved.id)

    def test_closest_plan_approved_not_set_on_fact_creation_when_multiple_plan_exists(self):
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(10, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(18, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(21, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(12, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        resp = self.client.post(self.url, self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        fact_id = resp.json()['id']
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.closest_plan_approved_id, None)


class TestAttendanceRecords(TestsHelperMixin, APITestCase):
    def setUp(self):
        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()

        create_departments_and_users(self)

        self.worker_day_plan_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        self.worker_day_plan_not_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        self.worker_day_fact_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 12, 23)),
            dttm_work_end=datetime.combine(self.dt, time(20, 2, 1)),
            parent_worker_day=self.worker_day_plan_approved,
            closest_plan_approved=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            closest_plan_approved=self.worker_day_plan_approved,
        )
        self.network.trust_tick_request = True
        self.network.save()

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
            employee=self.employee3,
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
            is_approved=False,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee3,
            source=WorkerDay.SOURCE_AUTO_FACT,
        )

        self.assertTrue(wd.exists())
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee3,
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
            employee=self.employee2
        )

        self.assertTrue(wd.exists())

    def test_attendancerecords_no_fact_create(self):
        self.network.skip_leaving_tick = True
        self.network.save()

        self.worker_day_fact_not_approved.delete()
        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(20, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2,
        )
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(20, 0, 0)),
            dttm_work_end=None,
            employee=self.employee2,
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
            employee=self.employee2
        ).first()
        self.assertIsNotNone(new_wd)
        self.assertTrue(new_wd.employment.id, self.employment2.id)

    def test_set_workday_type_for_existing_empty_types(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).update(
            type_id=WorkerDay.TYPE_EMPTY,
            dttm_work_start=None,
            dttm_work_end=None,
        )
        WorkerDayCashboxDetails.objects.filter(worker_day_id=self.worker_day_fact_approved.id).delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        fact_approved = WorkerDay.objects.get(id=self.worker_day_fact_approved.id)
        self.assertEqual(fact_approved.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(fact_approved.dttm_work_start, tm_start)
        self.assertEqual(fact_approved.dttm_work_end, None)
        fact_worker_day_details = fact_approved.worker_day_details.all()
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)

    def test_set_is_vacancy_as_True_if_shops_are_different(self):
        self.worker_day_fact_approved.delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user8
        )

        new_wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=tm_start,
            dttm_work_end=None,
            employee=self.employee8,
        ).last()
        self.assertEqual(new_wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(new_wd.dttm_work_start, tm_start)
        self.assertEqual(new_wd.dttm_work_end, None)
        self.assertEqual(new_wd.is_vacancy, True)

    def test_create_attendance_records_for_different_shops(self):
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        ar = AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        wd = WorkerDay.objects.filter(
            employee=ar.employee,
            is_fact=True,
            is_approved=True,
            dt=tm_start.date()
        ).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, None)
        self.assertEqual(wd.is_vacancy, True)

        tm_end = datetime.combine(self.dt, time(12, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_end,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop2,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, tm_end)
        self.assertEqual(wd.is_vacancy, True)

        tm_start2 = datetime.combine(self.dt, time(13, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start2,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop3,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, tm_end)
        self.assertEqual(wd.is_vacancy, True)

        tm_end2 = datetime.combine(self.dt, time(20, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_end2,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop3,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, tm_end2)
        self.assertEqual(wd.is_vacancy, True)

    def test_fact_work_type_received_from_plan_approved(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)

    def test_fact_work_type_received_from_plan_approved_when_shop_differs(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.select_related('work_type')
        self.assertEqual(len(plan_worker_day_details), 1)
        # shop2 wt
        WorkType.objects.create(
            shop=self.shop2,
            work_type_name=plan_worker_day_details[0].work_type.work_type_name,
        )
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2,
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertNotEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)
        self.assertEqual(
            fact_worker_day_details[0].work_type.work_type_name_id,
            plan_worker_day_details[0].work_type.work_type_name_id,
        )

    def test_fact_work_type_received_from_employment_if_there_is_no_plan(self):
        work_type_name = WorkTypeName.objects.create(
            name='Повар',
        )
        work_type_name2 = WorkTypeName.objects.create(
            name='Продавец',
        )
        work_type = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name,
        )
        work_type2 = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name2,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type,
            priority=10,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type2,
            priority=5,
        )
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, work_type.id)

    def test_work_type_created_for_holiday(self):
        work_type_name = WorkTypeName.objects.create(
            name='Повар',
        )
        work_type = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type,
            priority=10,
        )
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.worker_day_details.all().delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).update(
            type_id=WorkerDay.TYPE_HOLIDAY,
            dttm_work_start=None,
            dttm_work_end=None,
        )
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, work_type.id)

    def test_dt_changed_to_prev(self):
        self.worker_day_fact_approved.delete()
        record1 = AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            type=AttendanceRecords.TYPE_COMING,
            dttm=datetime.combine(self.dt, time(17, 54)),
        )
        record2 = AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            type=AttendanceRecords.TYPE_LEAVING,
            dttm=datetime.combine(self.dt + timedelta(1), time(1, 54)),
        )
        self.assertEqual(record1.dt, self.dt)
        self.assertEqual(record2.dt, self.dt)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt, time(17, 54)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt + timedelta(1), time(1, 54)))

    def test_create_second_record_for_prev_day_when_prev_fact_closed(self):
        self.worker_day_fact_approved.dt = self.dt
        self.worker_day_fact_approved.dttm_work_start = datetime.combine(self.dt, time(18, 34))
        self.worker_day_fact_approved.dttm_work_end = datetime.combine(self.dt + timedelta(1), time(1, 2))
        self.worker_day_fact_approved.save()
        AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            dttm=datetime.combine(self.dt + timedelta(1), time(1, 5)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).first().dttm_work_end,
                         datetime.combine(self.dt + timedelta(1), time(1, 5)))

    def test_create_att_record_and_update_not_approved(self):
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(11, 5)),
            type=AttendanceRecords.TYPE_COMING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee__user_id=self.user1.id).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved = WorkerDay.objects.get(is_approved=True, is_fact=True, employee=self.employee1)
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved.refresh_from_db()
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_end, datetime.combine(self.dt, time(14, 54)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(19, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved.refresh_from_db()
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_end, datetime.combine(self.dt, time(19, 54)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)

    def test_create_record_no_replace_not_approved_fact(self):
        self.network.skip_leaving_tick = False
        self.network.save()
        wd = WorkerDayFactory(
            dt=self.dt,
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            shop_id=self.employment1.shop_id,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(10, 5)),
            dttm_work_end=datetime.combine(self.dt, time(20, 10)),
            created_by=self.user1,
            last_edited_by=self.user1,
            is_fact=True,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 1)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd.refresh_from_db()
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt, time(10, 5)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt, time(20, 10)))
        self.assertTrue(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=self.dt, employee=self.employee1).exists())

    def test_create_attendance_record_fill_employment(self):
        attr = AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(attr.employee_id, self.employment1.employee_id)
        self.assertEqual(attr.dt, self.dt)
        WorkerDay.objects.update_or_create(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            is_approved=True,
            is_fact=False,
            defaults={
                'employment': self.employment2,
                'type_id': WorkerDay.TYPE_WORKDAY,
                'shop_id': self.employment2.shop_id,
                'dttm_work_start': datetime.combine(self.dt, time(10, 5)),
                'dttm_work_end': datetime.combine(self.dt, time(20, 10)),
            }
        )
        attr = AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            user_id=self.employment2.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
        )
        self.assertEqual(attr.employee_id, self.employment2.employee_id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_COMING)

    def test_create_attendance_record_with_two_near_workdays(self):
        WorkerDay.objects.update_or_create(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            is_approved=True,
            is_fact=False,
            defaults={
                'employment': self.employment2,
                'type_id': WorkerDay.TYPE_WORKDAY,
                'shop': self.shop,
                'dttm_work_start': datetime.combine(self.dt, time(10)),
                'dttm_work_end': datetime.combine(self.dt, time(16)),
            }
        )
        self.second_employee = Employee.objects.create(
            user=self.user2,
            tabel_code='1234',
        )
        self.second_employment = Employment.objects.create(
            employee=self.second_employee,
            shop_id=self.employment2.shop_id,
        )
        WorkerDay.objects.create(
            dt=self.dt,
            employee=self.second_employee,
            is_approved=True,
            is_fact=False,
            employment=self.second_employment,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(16)),
            dttm_work_end=datetime.combine(self.dt, time(22)),
        )
        attr = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(self.dt, time(15, 40)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(attr.employee_id, self.employment2.employee_id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_LEAVING)
        attr = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(self.dt, time(15, 41)),
            type=AttendanceRecords.TYPE_COMING,
        )
        self.assertEqual(attr.employee_id, self.second_employee.id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_COMING)

    def test_calc_day_and_night_work_hours_when_night_hours_is_less_than_half_of_break_time(self):
        self.worker_day_fact_approved.dttm_work_start = datetime.combine(self.dt, time(16))
        self.worker_day_fact_approved.dttm_work_end = datetime.combine(self.dt, time(22, 15))
        self.worker_day_fact_approved.save()
        total, day, night = self.worker_day_fact_approved.calc_day_and_night_work_hours()
        self.assertEqual(total, 5.25)
        self.assertEqual(day, 5.25)
        self.assertEqual(night, 0.0)

    def test_two_facts_created_when_there_are_two_plans(self):
        WorkerDay.objects.filter(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
        ).delete()
        WorkerDayFactory(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            is_approved=True,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(10)),
            dttm_work_end=datetime.combine(self.dt, time(13)),
        )
        WorkerDayFactory(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            is_approved=True,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(19)),
            dttm_work_end=datetime.combine(self.dt, time(22)),
        )

        dttm_start1 = datetime.combine(self.dt, time(9, 54))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_start1,
            type=AttendanceRecords.TYPE_COMING,
        )
        dttm_end1 = datetime.combine(self.dt, time(13, 2))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_end1,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertTrue(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            dttm_work_start=dttm_start1,
            dttm_work_end=dttm_end1,
            is_fact=True,
            is_approved=True,
        ).exists())

        dttm_start2 = datetime.combine(self.dt, time(18, 56))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_start2,
            type=AttendanceRecords.TYPE_COMING,
        )
        dttm_end2 = datetime.combine(self.dt, time(22, 6))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_end2,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertTrue(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            dttm_work_start=dttm_start2,
            dttm_work_end=dttm_end2,
            is_fact=True,
            is_approved=True,
        ).exists())
        self.assertEqual(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            is_fact=True,
            is_approved=True,
        ).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            is_fact=True,
            is_approved=False,
        ).count(), 2)

    def test_there_is_no_redundant_fact_approved_created_on_att_record_recalc(self):
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_plan_approved.id,
                self.worker_day_plan_not_approved.id,
            ],
        ).update(
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(10)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
        )
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_fact_approved.id,
                self.worker_day_fact_not_approved.id,
            ],
        ).delete()
        fact_dttm_start = datetime.combine(self.dt, time(9, 57))
        ar_start = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_start,
            type=AttendanceRecords.TYPE_COMING,
        )

        fact_qs = WorkerDay.objects.filter(
            employee_id=ar_start.employee_id,
            dt=self.dt,
            dttm_work_start=fact_dttm_start,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
        )
        fact_approved_qs = fact_qs.filter(is_approved=True)
        fact_approved = fact_approved_qs.get()
        fact_not_approved_qs = fact_qs.filter(is_approved=False)
        fact_not_approved = fact_not_approved_qs.get()
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertIsNone(fact_not_approved.last_edited_by_id)
        # при отметке должен был проставиться closest_plan_approved
        self.assertEqual(fact_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)

        manual_fact_dttm_end = datetime.combine(self.dt, time(20))
        resp = self._change_wd_data(fact_not_approved.id, data_to_change={'dttm_work_end': manual_fact_dttm_end})
        self.assertEqual(resp.status_code, 200)
        fact_not_approved.refresh_from_db()
        self.assertEqual(fact_not_approved.dttm_work_end, manual_fact_dttm_end)
        self.assertEqual(fact_not_approved.closest_plan_approved_id, self.worker_day_plan_approved.id)
        resp = self._approve(
            shop_id=fact_not_approved.shop_id,
            is_fact=True,
            dt_from=self.dt,
            dt_to=self.dt,
            employee_ids=[fact_not_approved.employee_id],
        )
        self.assertEqual(resp.status_code, 200)
        fact_not_approved.refresh_from_db()
        self.assertTrue(fact_not_approved.is_approved)
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertEqual(fact_not_approved.last_edited_by_id, self.user1.id)
        self.assertFalse(WorkerDay.objects.filter(id=fact_approved.id).exists())
        fact_approved = fact_not_approved
        fact_not_approved = fact_not_approved_qs.get()
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertEqual(fact_not_approved.last_edited_by_id, self.user1.id)
        # после подтв. факта должен быть проставлен closest_plan_approved в новом факте подтвежденном (бывшем черновике)
        self.assertEqual(fact_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)
        ar_start.refresh_from_db()

        new_plan_dttm_end = datetime.combine(self.dt, time(19))
        resp = self._change_wd_data(
            self.worker_day_plan_not_approved.id, data_to_change={'dttm_work_end': new_plan_dttm_end})
        self.assertEqual(resp.status_code, 200)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertEqual(self.worker_day_plan_not_approved.dttm_work_end, new_plan_dttm_end)
        resp = self._approve(
            shop_id=self.worker_day_plan_not_approved.shop_id,
            is_fact=False,
            dt_from=self.dt,
            dt_to=self.dt,
            employee_ids=[self.worker_day_plan_not_approved.employee_id],
        )
        self.assertEqual(resp.status_code, 200)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertTrue(self.worker_day_plan_not_approved.is_approved)
        plan_approved = self.worker_day_plan_not_approved
        # после подтверждения плана должен проставиться новый план подтвержденный (бывшый план черновик)
        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.closest_plan_approved.id, plan_approved.id)

        self.assertTrue(WorkerDay.objects.filter(id=fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=fact_not_approved.id).exists())

        # TODO: проверка, что автоматический пересчет факта на основе отметок запустится
        # пока вызовем пересчет отметки вручную
        ar_start.save()
        self.assertEqual(fact_approved_qs.count(), 1)  # не должен создаться дополнительный факт

    def test_night_shift_leaving_tick_diff_more_than_in_settings(self):
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_plan_approved.id,
                self.worker_day_plan_not_approved.id,
            ],
        ).update(
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt + timedelta(days=1), time(7)),
        )
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_fact_approved.id,
                self.worker_day_fact_not_approved.id,
            ],
        ).delete()

        fact_dttm_start = datetime.combine(self.dt, time(7, 47))
        ar_start = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_start,
            type=AttendanceRecords.TYPE_COMING,
        )

        fact_qs = WorkerDay.objects.filter(
            employee_id=ar_start.employee_id,
            dt=self.dt,
            dttm_work_start=fact_dttm_start,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
        )
        fact_approved_qs = fact_qs.filter(is_approved=True)
        fact_approved = fact_approved_qs.get()
        fact_not_approved_qs = fact_qs.filter(is_approved=False)
        fact_not_approved = fact_not_approved_qs.get()
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertIsNone(fact_not_approved.last_edited_by_id)
        # при отметке должен был проставиться closest_plan_approved
        self.assertEqual(fact_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)
        self.assertEqual(fact_not_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)

        fact_dttm_end = datetime.combine(self.dt + timedelta(days=1), time(1, 40))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_end,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.dttm_work_end, fact_dttm_end)

    def test_att_record_when_vacation_and_workday_in_plan(self):
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
        fact_dttm_start = datetime.combine(dt, time(7, 40))
        ar_start = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_start,
            type=AttendanceRecords.TYPE_COMING,
        )
        fact_dttm_end = datetime.combine(dt, time(21, 40))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_end,
            type=AttendanceRecords.TYPE_LEAVING,
        )

        fact_qs = WorkerDay.objects.filter(
            employee_id=ar_start.employee_id,
            dt=dt,
            dttm_work_start=fact_dttm_start,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
        )
        fact_approved_qs = fact_qs.filter(is_approved=True)
        fact_approved = fact_approved_qs.get()
        fact_not_approved_qs = fact_qs.filter(is_approved=False)
        fact_not_approved = fact_not_approved_qs.get()

        self.assertFalse(fact_approved.closest_plan_approved.type.is_dayoff)
        self.assertFalse(fact_not_approved.closest_plan_approved.type.is_dayoff)
        self.assertEqual(fact_approved.dttm_work_start, fact_dttm_start)
        self.assertEqual(fact_approved.dttm_work_end, fact_dttm_end)

    def test_create_attendance_records_when_closest_plan_does_not_exist(self):
        WorkerDay.objects.filter(employee=self.employee3).delete()
        wd_far_approved_fact = WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=True,
            dttm_work_start=datetime(2021, 9, 21, 8, 34),
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        record = AttendanceRecords.objects.create(
            employee=self.employee3,
            user=self.user3,
            dttm=datetime(2021, 11, 12, 21, 23),
            shop=self.shop,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEquals(record.dt, date(2021, 11, 12))
        wd_far_approved_fact.refresh_from_db()
        self.assertIsNone(wd_far_approved_fact.dttm_work_end)
        wd_created = WorkerDay.objects.filter(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 11, 12),
            is_approved=True,
            is_fact=True,
            type_id=WorkerDay.TYPE_WORKDAY,
        ).first()
        self.assertIsNotNone(wd_created)
        self.assertIsNone(wd_created.dttm_work_start)
        self.assertEquals(wd_created.dttm_work_end, datetime(2021, 11, 12, 21, 23))


class TestVacancy(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/vacancy/'
        cls.create_departments_and_users()
        cls.network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'I': 'подразделение',
                    'R': 'подразделения',
                    'P': 'подразделении',
                }
            }
        )
        cls.network.save()
        cls.dt_now = date.today()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.vacancy = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee1,
            employment=cls.employment1,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
            comment='Test',
        )
        cls.vacancy2 = WorkerDay.objects.create(
            shop=cls.shop,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
            is_approved=True,
            comment='Test',
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
            'employee_id': None
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
        self.assertEqual(response.json()['results'][0]['comment'], 'Test')

    def test_get_list_shift_length(self):
        response = self.client.get(
            f'{self.url}?shop_id={self.shop.id}&shift_length_min=7:00:00&shift_length_max=9:00:00&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_vacant_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_vacant=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_outsource_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 2)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)
        self.vacancy2.is_outsource = True
        self.vacancy2.save()
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=false&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_confirm_vacancy(self):
        event, _ = EventType.objects.get_or_create(
            code=VACANCY_CONFIRMED_TYPE,
            network=self.network,
        )
        subject = 'Сотрудник откликнулся на вакансию.'
        event_notification = EventEmailNotification.objects.create(
            event_type=event,
            subject=subject,
            system_email_template='notifications/email/vacancy_confirmed.html',
        )
        self.user1.email = 'test@mail.mm'
        self.user1.save()
        event_notification.users.add(self.user1)
        self.shop.__class__.objects.filter(id=self.shop.id).update(email=True)
        pnawd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
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
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
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
        self.add_group_perm(self.employee_group, 'WorkerDay_confirm_vacancy', 'POST')
        response = self.client.post(f'/rest_api/worker_day/{self.vacancy2.id}/confirm_vacancy/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, subject)
        self.assertEqual(mail.outbox[0].to[0], self.user1.email)
        self.assertEqual(
            mail.outbox[0].body,
            f'Здравствуйте, {self.user1.first_name}!\n\n\n\n\n\n\nСотрудник {self.user2.last_name} {self.user2.first_name} откликнулся на вакансию с типом работ {self.work_type1.work_type_name.name}\n'
            f'Дата: {self.vacancy2.dt}\nПодразделение: {self.shop.name}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )

        self.assertFalse(WorkerDay.objects.filter(id=pawd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(is_approved=False, dt=self.vacancy2.dt, employee=self.employee2).exists())

        # можно откликнуться на вакансию,
        # если время не пересекается с другой вакансией на которую уже откликнулся или назначен
        vacancy3 = WorkerDayFactory(
            employee_id=None,
            employment_id=None,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now, time(18)),
            dttm_work_end=datetime.combine(self.dt_now, time(22)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_approved=True,
            cashbox_details__work_type=self.work_type1,
        )
        response = self.client.post(f'/rest_api/worker_day/{vacancy3.id}/confirm_vacancy/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})

        # нельзя откликнуться на вакансию,
        # если время вакансии пересекается с другой/другими днями
        vacancy4 = WorkerDayFactory(
            employee_id=None,
            employment_id=None,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now, time(12)),
            dttm_work_end=datetime.combine(self.dt_now, time(22)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_approved=True,
            cashbox_details__work_type=self.work_type1,
        )
        response = self.client.post(f'/rest_api/worker_day/{vacancy4.id}/confirm_vacancy/')
        self.assertContains(
            response, text='Операция не может быть выполнена. Недопустимое пересечение времени', status_code=400)

    def test_approve_vacancy(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(employee_id=None, is_approved=False)
        wd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.vacancy.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.vacancy.id, is_approved=True).exists())

        WorkerDay.objects.filter(id=self.vacancy.id).update(employee=wd.employee, is_approved=False)

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(WorkerDay.objects.filter(id=wd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.vacancy.id, is_approved=True).exists())
        self.assertTrue(WorkerDay.objects.filter(
            dt=self.vacancy.dt,
            employee_id=self.vacancy.employee_id,
            is_fact=self.vacancy.is_fact,
            is_approved=True,
        ).exists())

    def test_get_only_available(self):
        '''
        Создаем дополнительно 3 вакансии на 3 дня вперед
        Вернется только одна вакансия, так как:
        1. У сотрудника подтвержденный рабочий день
        2. У сотрудника нет подтвержденного плана
        3. Сотрудник уволен до даты вакансии
        '''
        WorkerDay.objects.create(
            employee=self.employment1.employee,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employment1.employee,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(1), time(hour=11, minute=30)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(1), time(hour=20, minute=30)),
            dt=self.dt_now + timedelta(1),
            is_approved=False,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(1), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(1), time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(1),
            is_vacancy=True,
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(2), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(2), time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(2),
            is_vacancy=True,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.employment1.employee,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now + timedelta(3),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(2), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(2), time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(3),
            is_vacancy=True,
            is_approved=True,
        )
        self.employment1.dt_fired = self.dt_now + timedelta(2)
        self.employment1.save()
        resp = self.client.get('/rest_api/worker_day/vacancy/?only_available=true&offset=0&limit=10&is_vacant=true')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['dt'], self.dt_now.strftime('%Y-%m-%d'))

    def test_update_vacancy_type_to_deleted(self):
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop2,
        )
        vacancy = WorkerDay.objects.create(
            shop=self.shop2,
            employee=self.employee2,
            employment=self.employment2,
            dttm_work_start=datetime.combine(self.dt_now, time(9)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            comment='Test',
        )
        response = self.client.put(
            f'/rest_api/worker_day/{vacancy.id}/',
            {
                "dt": vacancy.dt,
                "is_fact": False,
                "type": WorkerDay.TYPE_EMPTY,
            }
        )
        self.assertEquals(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertFalse(vacancy.is_vacancy)
        response = self.client.put(
            f'/rest_api/worker_day/{vacancy.id}/',
            self.dump_data(
                {
                    "employee_id": self.employee2.id,
                    "shop_id": self.shop2.id,
                    "dt": vacancy.dt,
                    "dttm_work_start": datetime.combine(vacancy.dt, time(8, 0, 0)),
                    "dttm_work_end": datetime.combine(vacancy.dt, time(20, 0, 0)),
                    "type": WorkerDay.TYPE_WORKDAY,
                    "is_fact": False,
                    "worker_day_details": [
                        {
                            "work_part": 1.0,
                            "work_type_id": self.work_type.id
                        },
                    ]
                }
            ),
            content_type='application/json',
        )
        self.assertEquals(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertTrue(vacancy.is_vacancy)
    
    def test_cost_per_hour_in_list(self):
        self.vacancy.cost_per_hour = 120120.45
        self.vacancy.save()
        response = self.client.get(f"{self.url}?limit=100")
        vacancy = list(filter(lambda x: x['id'] == self.vacancy.id, response.json()['results']))[0]
        self.assertEquals(vacancy['cost_per_hour'], '120120.45')
        self.assertEquals(vacancy['total_cost'], 1171174.3875)
        

class TestAditionalFunctions(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    maxDiff = None

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

    def update_or_create_holidays(self, employment, dt_from, count, approved, wds={}):
        result = {}
        for day in range(count):
            dt = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(dt, None)
            result[dt] = WorkerDay.objects.create(
                employee=employment.employee,
                employment=employment,
                shop=None,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
        return result

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm, approved, wds={}, is_blocked=False, night_shift=False, shop_id=None):
        result = {}
        for day in range(count):
            date = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(date, None)
            date_to = date + timedelta(1) if night_shift else date
            wd = WorkerDay.objects.create(
                employment=employment,
                employee=employment.employee,
                shop_id=shop_id or employment.shop_id,
                dt=date,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(date, time(from_tm)),
                dttm_work_end=datetime.combine(date_to, time(to_tm)),
                is_approved=approved,
                parent_worker_day=parent_worker_day,
                is_blocked=is_blocked,
            )
            result[date] = wd

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        return result

    def test_delete(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 2, 16, 20, False)
        self.create_worker_days(self.employment2, dt_from + timedelta(2), 1, 16, 20, False, shop_id=self.shop2.id)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(3), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids':[self.employment2.employee_id, self.employment3.employee_id],
            'dates':[
                dt_from + timedelta(i)
                for i in range(3)
            ]
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 2)

    def test_delete_exclude_other_shops(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 2, 16, 20, False)
        self.create_worker_days(self.employment2, dt_from + timedelta(2), 1, 16, 20, False, shop_id=self.shop2.id)
        self.create_worker_days(self.employment3, dt_from, 2, 10, 21, False)
        self.create_worker_days(self.employment3, dt_from + timedelta(2), 2, 10, 21, False, shop_id=self.shop2.id)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(3), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids':[self.employment2.employee_id, self.employment3.employee_id],
            'dates':[
                dt_from + timedelta(i)
                for i in range(3)
            ],
            'shop_id': self.shop.id,
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, shop_id=self.shop.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, shop_id=self.shop2.id).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, shop_id=None).count(), 1)
    
    def test_delete_fact(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 3, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        WorkerDay.objects.all().update(is_fact=True)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(3), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids': [self.employment2.employee_id, self.employment3.employee_id],
            'dates': [
                dt_from + timedelta(i)
                for i in range(3)
            ]
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 8)

        data['is_fact'] = True
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 2)

    def test_exchange_approved(self):
        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(response.json()[0]['is_approved'], True)
        self.assertEqual(WorkerDay.objects.count(), 8)
        self.assertEqual(WorkerDay.objects.filter(source=WorkerDay.SOURCE_EXCHANGE_APPROVED).count(), 8)

    def test_cant_exchange_approved_and_protected_without_perm(self):
        dt_from = date.today()
        dates = [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)]
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': dates,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True, is_blocked=True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True, is_blocked=True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 403)
        dates_str = ','.join(dates)
        self.assertEqual(
            response.json()['detail'],
            'У вас нет прав на подтверждение защищенных рабочих дней ('
            f'{self.user2.last_name} {self.user2.first_name} ({self.user2.username}): {dates_str}, '
            f'{self.user3.last_name} {self.user3.first_name} ({self.user3.username}): {dates_str}'
            '). Обратитесь, пожалуйста, к администратору системы.',
        )

    def test_can_exchange_approved_and_protected_with_perm(self):
        self.admin_group.has_perm_to_change_protected_wdays = True
        self.admin_group.save()

        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True, is_blocked=True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True, is_blocked=True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(response.json()[0]['is_approved'], True)
        self.assertEqual(WorkerDay.objects.count(), 8)

    def test_doctors_schedule_send_on_exchange_approved(self):
        with self.settings(SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE=True, CELERY_TASK_ALWAYS_EAGER=True):
            from src.celery.tasks import send_doctors_schedule_to_mis
            with mock.patch.object(send_doctors_schedule_to_mis, 'delay') as send_doctors_schedule_to_mis_delay:
                dt_from = date.today()
                data = {
                    'employee1_id': self.employee2.id,
                    'employee2_id': self.employee3.id,
                    'dates': [
                        Converter.convert_date(dt_from + timedelta(i)) for i in range(-2, 4)
                    ],
                }
                # другой тип работ -- не отправляется
                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from - timedelta(days=2), is_approved=True,
                    cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                    cashbox_details__work_type__work_type_name__code='consult',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from - timedelta(days=2), is_approved=True,
                )

                wd_create_user3_and_delete_user2 = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from - timedelta(days=1), is_approved=True,
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from - timedelta(days=1), is_approved=True,
                )

                wd_update_user3 = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from, is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                wd_update_user2 = WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from, is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(20, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )

                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from + timedelta(days=1), is_approved=True,
                )
                wd_create_user2_and_delete_user3 = WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=1), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(11, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )

                # не рабочие дни -- не отправляется
                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from + timedelta(days=2), is_approved=True,
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_VACATION, shop=self.shop, dt=dt_from + timedelta(days=2), is_approved=True,
                )

                wd_create_user3_and_delete_user2_diff_work_types = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=3), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from + timedelta(days=3), time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from + timedelta(days=3), time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=3), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from + timedelta(days=3), time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from + timedelta(days=3), time(20, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                    cashbox_details__work_type__work_type_name__code='consult',
                )

                with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                    url = f'{self.url}exchange_approved/'
                    response = self.client.post(url, data, format='json')
                send_doctors_schedule_to_mis_delay.assert_called_once()
                json_data = json.loads(send_doctors_schedule_to_mis_delay.call_args[1]['json_data'])
                self.assertListEqual(
                    sorted(json_data, key=lambda i: (i['dt'], i['employee__user__username'])),
                    sorted([
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_end),
                            "action": "delete"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_end),
                            "action": "create"
                        },
                        {
                            "dt": Converter.convert_date(wd_update_user2.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_update_user2.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_update_user2.dttm_work_end),
                            "action": "update"
                        },
                        {
                            "dt": Converter.convert_date(wd_update_user3.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_update_user3.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_update_user3.dttm_work_end),
                            "action": "update"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user2_and_delete_user3.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_end),
                            "action": "create"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user2_and_delete_user3.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_end),
                            "action": "delete"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2_diff_work_types.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_end),
                            "action": "delete"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2_diff_work_types.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_end),
                            "action": "create"
                        },
                    ], key=lambda i: (i['dt'], i['employee__user__username']))
                )

                self.assertEqual(len(response.json()), 12)
                self.assertEqual(WorkerDay.objects.count(), 12)

    def test_exchange_with_holidays(self):
        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(2)],
        }
        self.create_worker_days(self.employment2, dt_from, 1, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from + timedelta(1), 1, 9, 21, True)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(1), 1, True)
        self.update_or_create_holidays(self.employment3, dt_from, 1, True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 4)
        employment3_worker_day = list(filter(lambda x: x['employment_id'] == self.employment3.id and x['type'] == WorkerDay.TYPE_WORKDAY, data))[0]
        self.assertEquals(employment3_worker_day['shop_id'], self.employment3.shop.id)
        self.assertEquals(employment3_worker_day['work_hours'], '08:45:00')
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_HOLIDAY, dt=dt_from, is_approved=True, employment=self.employment2).exists())
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_WORKDAY, dt=dt_from + timedelta(1), is_approved=True, employment=self.employment2).exists())
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_WORKDAY, dt=dt_from, is_approved=True, employment=self.employment3).exists())
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_HOLIDAY, dt=dt_from + timedelta(1), is_approved=True, employment=self.employment3).exists())

    def test_exchange_not_approved(self):
        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        url = f'{self.url}exchange/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.count(), 16)
        self.assertEqual(WorkerDay.objects.filter(source=WorkerDay.SOURCE_EXCHANGE, is_approved=False).count(), 8)

    def test_duplicate_full(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False, source=WorkerDay.SOURCE_DUPLICATE).count(), 5)

    def test_duplicate_less(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 4)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 5)

    def test_duplicate_more(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(10)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(8)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)

    def test_duplicate_for_different_start_dates(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)

    def test_duplicate_day_without_time(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)
        self.update_or_create_holidays(self.employment2, dt_from, 1, False)

        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(1)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)

    def test_cant_duplicate_when_there_is_no_active_employment(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)

        Employment.objects.filter(id=self.employment3.id).update(
            dt_hired=dt_from - timedelta(days=30),
            dt_fired=dt_from2,
        )

        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0],
            'Невозможно создать дни в выбранные даты. Пожалуйста, '
            'проверьте наличие активного трудоустройства у сотрудника.'
        )
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 0)

    def test_duplicate_night_shifts(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 20, 10, True, night_shift=True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False, work_hours__gt=timedelta(0)).count(), 5)
        wd = WorkerDay.objects.filter(employee=self.employee3, is_approved=False).order_by('dt').first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(dt_from, time(20)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(dt_from + timedelta(1), time(10)))

    def test_the_order_of_days_is_determined_by_day_date_not_by_the_date_of_creation(self):
        dt_now = date.today()
        dt_tomorrow = dt_now + timedelta(days=1)
        dt_to = dt_now + timedelta(days=5)

        wd_dt_tomorrow = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt_tomorrow,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_now, time(8, 0, 0)),
            dttm_work_end=datetime.combine(dt_now, time(20, 0, 0)),
            is_fact=False,
            is_approved=False,
        )
        wd_dt_now = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt_now,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_fact=False,
            is_approved=False,
        )

        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [wd_dt_now.dt, wd_dt_tomorrow.dt],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_to + timedelta(days=i)) for i in range(2)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee3, is_approved=False, dt=dt_to, type='H'
        ).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee3, is_approved=False, dt=dt_to + timedelta(days=1), type_id='W'
        ).count(), 1)

    def test_copy_approved(self):
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        WorkerDay.objects.create(
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=True,
            dt=dt_now + timedelta(1),
        )
        self.create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        self.update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        self.create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        self.update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)

        data = {
            'employee_ids': [
                self.employment1.employee_id,
                self.employment3.employee_id,
            ],
            'dates': [
                dt_now + timedelta(days=i)
                for i in range(6)
            ]
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 12)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, source=WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_PLAN).count(), 12)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_approved_to_fact(self):
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        self.create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        self.update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        self.create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        self.update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)
        WorkerDay.objects.create(
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            dt=dt_now,
            type_id=WorkerDay.TYPE_EMPTY,
            shop_id=self.employment1.shop_id,
            is_fact=True,
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
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 1)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 7)
        self.assertEqual(WorkerDay.objects.filter(
            is_approved=False, is_fact=True, work_hours__gt=timedelta(seconds=0), source=WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_FACT).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_approved_fact_to_fact(self):
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        self.create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        self.update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        self.create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        self.update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)
        WorkerDay.objects.filter(
            type_id=WorkerDay.TYPE_WORKDAY,
        ).update(
            is_fact=True,
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
            'type': 'FF',
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, source=WorkerDay.SOURCE_COPY_APPROVED_FACT_TO_FACT).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_range(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + relativedelta(day=31)
        dt_to_first = dt_from_first + relativedelta(months=1)
        dt_to_last = dt_to_first + relativedelta(day=31)

        for i in range((dt_from_last - dt_from_first).days + 1):
            dt = dt_from_first + timedelta(i)
            type_id = WorkerDay.TYPE_WORKDAY if i % 3 != 0 else WorkerDay.TYPE_HOLIDAY
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type_id=type_id,
                is_approved=True,
            )
            if i % 2 == 0 and i < 28:
                WorkerDay.objects.create(
                    dt=dt,
                    shop_id=self.employment2.shop_id,
                    employee_id=self.employment2.employee_id,
                    employment=self.employment2,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    is_approved=True,
                    is_fact=True,
                )
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment3.shop_id,
                employee_id=self.employment3.employee_id,
                employment=self.employment3,
                type_id=type_id,
                is_approved=True,
            )
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment4.shop_id,
                employee_id=self.employment4.employee_id,
                employment=self.employment4,
                type_id=type_id,
                is_approved=True,
            )

        data = {
            'employee_ids': [
                self.employment2.employee_id,
                self.employment4.employee_id,
            ],
            'from_copy_dt_from': dt_from_first,
            'from_copy_dt_to': dt_from_last,
            'to_copy_dt_from': dt_to_first,
            'to_copy_dt_to': dt_to_last,
            'is_approved': True,
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), ((dt_from_last - dt_from_first).days + 1) * 3 + 14)
        response = self.client.post(self.url + 'copy_range/', data=data)
        response_data = response.json()

        self.assertEqual(len(response_data), ((dt_to_last - dt_to_first).days + 1) * 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, source=WorkerDay.SOURCE_COPY_RANGE).count(), ((dt_to_last - dt_to_first).days + 1) * 2)
        self.assertEqual(
            list(WorkerDay.objects.filter(
                is_fact=False,
                is_approved=False,
                dt__gte=dt_to_first,
                dt__lte=dt_to_last,
            ).order_by(
                'employee__user_id',
            ).values_list(
                'employee__user_id',
                flat=True,
            ).distinct()),
            [self.employment2.employee.user_id, self.employment4.employee.user_id],
        )

    def test_copy_range_types_and_more(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + timedelta(4)
        dt_to_first = dt_from_last + timedelta(1)
        dt_to_last = dt_to_first + timedelta(7)

        for i in range(5):
            # H,W,W,H,W
            dt = dt_from_first + timedelta(i)
            type_id = WorkerDay.TYPE_WORKDAY if i % 3 != 0 else WorkerDay.TYPE_HOLIDAY
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type_id=type_id,
                is_approved=False,
            )
        for i in range(8):
            dt = dt_to_first + timedelta(i)
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        data = {
            'employee_ids': [
                self.employment2.employee_id,
            ],
            'from_copy_dt_from': dt_from_first,
            'from_copy_dt_to': dt_from_last,
            'to_copy_dt_from': dt_to_first,
            'to_copy_dt_to': dt_to_last,
            'worker_day_types': ['W'],
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 13)
        response = self.client.post(self.url + 'copy_range/', data=data)
        response_data = response.json()

        self.assertEqual(len(response_data), 5)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, type='V').count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, type='W').count(), 5)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, type='H').count(), 0)

    def test_copy_range_bad_dates(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + relativedelta(day=31)
        dt_to_first = dt_from_first - timedelta(1)
        dt_to_last = dt_to_first + relativedelta(day=31)
        data = {
            'employee_ids': [
                self.employment2.employee_id,
                self.employment4.employee_id,
            ],
            'from_copy_dt_from': dt_from_first,
            'from_copy_dt_to': dt_from_last,
            'to_copy_dt_from': dt_to_first,
            'to_copy_dt_to': dt_to_last,
        }
        response = self.client.post(self.url + 'copy_range/', data=data)
        self.assertEqual(response.json(), ['Начало периода с которого копируются дни не может быть больше начала периода куда копируются дни.'])

    def test_block_worker_day(self):
        dt_now = date.today()
        wd = WorkerDayFactory(
            dt=dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            is_fact=True,
        )
        data = {
            'worker_days': [
                {
                    'worker_username': wd.employee.user.username,
                    'shop_code': wd.shop.code,
                    'dt': Converter.convert_date(dt_now),
                    'is_fact': True,
                },
            ]
        }

        response = self.client.post(self.url + 'block/', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_blocked)

    def test_unblock_worker_day(self):
        dt_now = date.today()
        wd = WorkerDayFactory(
            dt=dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            is_fact=True,
            is_blocked=True,
        )
        data = {
            'worker_days': [
                {
                    'worker_username': wd.employee.user.username,
                    'shop_code': wd.shop.code,
                    'dt': Converter.convert_date(dt_now),
                    'is_fact': True,
                },
            ]
        }
        response = self.client.post(self.url + 'unblock/', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertFalse(wd.is_blocked)

    def test_change_list_create_vacancy(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
            'outsources': None,
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 10)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False, source=WorkerDay.SOURCE_CHANGE_LIST).count(), 10)

    def test_change_list_create_vacancy_with_employee(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'employee_id': self.employee1.id,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 10)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False, employee_id=self.employee1.id).count(), 10)

    def test_change_list_create_vacancy_with_outsources(self):
        dt_from = date.today()
        outsource_network1 = Network.objects.create(
            name='O1',
        )
        outsource_network2 = Network.objects.create(
            name='O2',
        )
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
            'outsources': [outsource_network1.id, outsource_network2.id],
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 10)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=True).count(), 10)
        self.assertCountEqual(
            list(
                WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=True).first().outsources.all()
            ), 
            [outsource_network1, outsource_network2],
        )

    def test_change_list_create_vacancy_weekdays(self):
        dt_from = date(2021, 7, 20)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
            'days_of_week': [0, 3, 6]
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 4)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).count(), 4)
        self.assertEquals(
            list(
                WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).order_by('dt').values_list('dt', flat=True)
            ),
            [date(2021, 7, 22), date(2021, 7, 25), date(2021, 7, 26), date(2021, 7, 29)]
        )

    def test_change_list_create_vacation(self):
        dt_from = date(2021, 1, 1)
        dt_to = date(2021, 1, 31)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_VACATION,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'employee_id': self.employee1.id,
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 31)
        self.assertEquals(WorkerDay.objects.filter(employee_id=self.employee1.id, type_id=WorkerDay.TYPE_VACATION, dt__gte=dt_from, dt__lte=dt_to, source=WorkerDay.SOURCE_CHANGE_LIST).count(), 31)

    def test_change_list_create_vacancy_many_work_types(self):
        dt_from = date.today()
        work_type_name2 = WorkTypeName.objects.create(name='Магазин2', network=self.network)
        work_type2 = WorkType.objects.create(
            work_type_name=work_type_name2,
            shop=self.shop)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 0.5,
                },
                {
                    'work_type_id': work_type2.id,
                    'work_part': 0.5,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 10)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).count(), 10)
        self.assertEquals(WorkerDayCashboxDetails.objects.count(), 20)

    def test_change_list_create_night_shifts_vacancy(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '20:00:00',
            'tm_work_end': '08:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                },
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEquals(len(data), 10)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).count(), 10)
        wd = WorkerDay.objects.filter(dt=dt_from).first()
        self.assertEquals(wd.dttm_work_start, datetime.combine(dt_from, time(20)))
        self.assertEquals(wd.dttm_work_end, datetime.combine(dt_from + timedelta(1), time(8)))

    def test_change_list_errors(self):
        dt_from = date(2021, 1, 1)
        dt_to = date(2021, 1, 2)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'dt_from': dt_from,
            'dt_to': dt_to,
        }
        url = f'{self.url}change_list/'
        # no tm_start
        response = self.client.post(url, data, format='json')
        self.assertEquals(response.status_code, 400)
        self.assertEquals(response.json(), {'tm_work_start': 'Это поле обязательно.'})
        data['tm_work_start'] = '10:00:00'
        # no tm_end
        response = self.client.post(url, data, format='json')
        self.assertEquals(response.status_code, 400)
        self.assertEquals(response.json(), {'tm_work_end': 'Это поле обязательно.'})
        data['tm_work_end'] = '20:00:00'
        # no cashbox_details
        response = self.client.post(url, data, format='json')
        self.assertEquals(response.status_code, 400)
        self.assertEquals(response.json(), {'cashbox_details': 'Это поле обязательно.'})
        data['cashbox_details'] = [
            {
                'work_type_id': self.work_type.id,
                'work_part': 1,
            }
        ]
        # no employee_id
        response = self.client.post(url, data, format='json')
        self.assertEquals(response.status_code, 400)
        self.assertEquals(response.json(), {'employee_id': 'Это поле обязательно.'})
        data['type'] = WorkerDay.TYPE_VACATION
        response = self.client.post(url, data, format='json')
        self.assertEquals(response.status_code, 400)
        self.assertEquals(response.json(), {'employee_id': 'Это поле обязательно.'})

    def test_recalc(self):
        today = date.today()
        wd = WorkerDayFactory(
            dt=today,
            type_id=WorkerDay.TYPE_WORKDAY,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.employment2.shop,
            is_approved=True,
            is_fact=True,
            dttm_work_start=datetime.combine(today, time(10)),
            dttm_work_end=datetime.combine(today, time(19)),
        )
        self.assertEqual(wd.work_hours, timedelta(hours=8))
        self.add_group_perm(self.employee_group, 'WorkerDay_recalc', 'POST')

        WorkerDay.objects.filter(id=wd.id).update(work_hours=timedelta(0))
        wd.refresh_from_db()
        self.assertEqual(wd.work_hours, timedelta(0))
        data = {
            'shop_id': wd.employment.shop_id,
            'employee_id__in': [self.employee2.id],
            'dt_from': today,
            'dt_to': today,
        }
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                path=self.get_url('WorkerDay-recalc'),
                data=self.dump_data(data), content_type='application/json',
            )
        self.assertContains(resp, 'Пересчет часов успешно запущен.', status_code=200)
        wd.refresh_from_db()
        self.assertEqual(wd.work_hours, timedelta(hours=8))

        data['employee_id__in'] = [self.employee8.id]
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            resp2 = self.client.post(
                path=self.get_url('WorkerDay-recalc'),
                data=self.dump_data(data), content_type='application/json',
            )
        self.assertContains(resp2, 'Не найдено сотрудников удовлетворяющих условиям запроса.', status_code=400)

    def test_duplicate_for_multiple_wdays_on_one_date(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 14, True)
        self.create_worker_days(self.employment2, dt_from, 5, 18, 22, True)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 14, False)
        self.create_worker_days(self.employment3, dt_from, 4, 18, 22, False)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 10)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 10)

    def test_duplicate_work_days_with_manual_work_hours(self):
        dt_now = date.today()
        WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_SICK,
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=dt_now,
            type_id=WorkerDay.TYPE_SICK,
            is_approved=False,
            is_fact=False,
            work_hours=timedelta(hours=12),
        )
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_now)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_now + timedelta(i)) for i in range(5)],
            'is_approved': False,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 5)
        self.assertEqual(WorkerDay.objects.get(id=resp_data[0]['id']).work_hours, timedelta(hours=12))


class TestFineLogic(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.network = Network.objects.create(name='Test')
        cls.shop = Shop.objects.create(
            name='Shop',
            network=cls.network,
            region=Region.objects.create(name='Def'),
        )
        cls.network.fines_settings = json.dumps(
           {
                r'(.*)?директор|управляющий(.*)?': {
                    'arrive_fines': [[-5, 10, 60], [60, 3600, 120]],
                    'departure_fines': [[-5, 10, 60], [60, 3600, 120]],
                },
                r'(.*)?кладовщик|курьер(.*)?': {
                    'arrive_fines': [[0, 10, 30], [30, 3600, 60]],
                    'departure_fines': [[-10, 10, 30], [60, 3600, 60]],
                },
                r'(.*)?продавец|кассир|менеджер|консультант(.*)?': {
                    'arrive_fines': [[-4, 60, 60], [60, 120, 120]],
                    'departure_fines': [],
                },
            }
        )
        cls.network.save()
        cls.breaks = Break.objects.create(
            name='brk',
            value='[[0, 3600, [30]]]',
        )
        cls.cashier = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Продавец-кассир', breaks=cls.breaks), 'Cashier', 'cashier')
        cls.dir = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Директор Магазина', breaks=cls.breaks), 'Dir', 'dir')
        cls.courier = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Курьер', breaks=cls.breaks), 'Courier', 'courier')
        cls.cleaner = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Уборщик', breaks=cls.breaks), 'Cleaner', 'cleaner')

    def setUp(self):
        self.network.refresh_from_db()

    def _create_user(self, position, last_name, username):
        user = User.objects.create(
            last_name=last_name,
            username=username,
        )
        employee = Employee.objects.create(
            user=user,
            tabel_code=username,
        )
        employment = Employment.objects.create(
            employee=employee,
            position=position,
            shop=self.shop,
        )
        return user, employee, employment

    def _create_or_update_worker_day(self, employment, dttm_from, dttm_to, is_fact=False, is_approved=True, closest_plan_approved_id=None):
        wd, _ =  WorkerDay.objects.update_or_create(
            employee_id=employment.employee_id,
            is_fact=is_fact,
            is_approved=is_approved,
            dt=dttm_from.date(),
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            defaults=dict(
                dttm_work_start=dttm_from,
                dttm_work_end=dttm_to,
                employment=employment,
            ),
            closest_plan_approved_id=closest_plan_approved_id,
        )
        return wd

    def test_fine_settings(self):
        dt = date.today()
        plan_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEquals(plan_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 53)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEquals(fact_wd_dir.work_hours, timedelta(hours=9, minutes=47))
        fact_wd_dir_bad = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEquals(fact_wd_dir_bad.work_hours, timedelta(hours=7, minutes=34))

        plan_wd_cashier = self._create_or_update_worker_day(self.cashier[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEquals(plan_wd_cashier.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_cashier = self._create_or_update_worker_day(self.cashier[2], datetime.combine(dt, time(9, 55)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_cashier.id)
        self.assertEquals(fact_wd_cashier.work_hours, timedelta(hours=9, minutes=45))
        fact_wd_cashier_bad = self._create_or_update_worker_day(self.cashier[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_cashier.id)
        self.assertEquals(fact_wd_cashier_bad.work_hours, timedelta(hours=8, minutes=34))

        plan_wd_courier = self._create_or_update_worker_day(self.courier[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEquals(plan_wd_courier.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_courier = self._create_or_update_worker_day(self.courier[2], datetime.combine(dt, time(9, 55)), datetime.combine(dt, time(20, 11)), is_fact=True, closest_plan_approved_id=plan_wd_courier.id)
        self.assertEquals(fact_wd_courier.work_hours, timedelta(hours=9, minutes=46))
        fact_wd_courier_bad = self._create_or_update_worker_day(self.courier[2], datetime.combine(dt, time(10, 1)), datetime.combine(dt, time(19, 50)), is_fact=True, closest_plan_approved_id=plan_wd_courier.id)
        self.assertEquals(fact_wd_courier_bad.work_hours, timedelta(hours=8, minutes=19))

        plan_wd_cleaner = self._create_or_update_worker_day(self.cleaner[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEquals(plan_wd_cleaner.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_cleaner = self._create_or_update_worker_day(self.cleaner[2], datetime.combine(dt, time(9, 55)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_cleaner.id)
        self.assertEquals(fact_wd_cleaner.work_hours, timedelta(hours=9, minutes=45))
        fact_wd_cleaner_bad = self._create_or_update_worker_day(self.cleaner[2], datetime.combine(dt, time(10, 5)), datetime.combine(dt, time(19, 50)), is_fact=True, closest_plan_approved_id=plan_wd_cleaner.id)
        self.assertEquals(fact_wd_cleaner_bad.work_hours, timedelta(hours=9, minutes=15))

    def test_facts_work_hours_recalculated_on_plan_change(self):
        dt = date.today()
        plan_approved = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9)), datetime.combine(dt, time(20)))

        fact_approved = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(8, 35)), datetime.combine(dt, time(20, 25)), is_fact=True, closest_plan_approved_id=plan_approved.id)
        self.assertEqual(fact_approved.work_hours.total_seconds(), 11 * 3600 + 20 * 60)

        fact_not_approved = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9)), datetime.combine(dt, time(19)), is_approved=False, is_fact=True, closest_plan_approved_id=plan_approved.id)
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 6 * 3600 + 30 * 60)

        plan_approved.dttm_work_start = datetime.combine(dt, time(11, 00, 0))
        plan_approved.dttm_work_end = datetime.combine(dt, time(17, 00, 0))
        plan_approved.save()

        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.work_hours.total_seconds(), 11 * 3600 + 20 * 60)
        fact_not_approved.refresh_from_db()
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 9 * 3600 + 30 * 60)

    def test_fine_settings_only_work_hours_that_in_plan(self):
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        dt = date.today()
        plan_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEquals(plan_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 53)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEquals(fact_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir_bad = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEquals(fact_wd_dir_bad.work_hours, timedelta(hours=7, minutes=30))

    def test_fine_settings_crop_work_hours_by_shop_schedule(self):
        self.network.crop_work_hours_by_shop_schedule = True
        self.network.save()
        dt = date.today()
        ShopSchedule.objects.create(
            dt=dt,
            shop=self.shop,
            opens='10:00:00',
            closes='20:00:00',
        )
        plan_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEquals(plan_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 53)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEquals(fact_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir_bad = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEquals(fact_wd_dir_bad.work_hours, timedelta(hours=7, minutes=30))


class TestUnaccountedOvertimesAPI(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.dt = date.today()
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        pa1 = self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(13)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(1)),
            is_approved=True,
        )
        pa2 = self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        pa3 = self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
        )
        # переработка 3 часа
        self._create_worker_day(
            self.employment2,
            dttm_work_start=datetime.combine(self.dt, time(12)),
            dttm_work_end=datetime.combine(self.dt + timedelta(1), time(3)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa1.id,
        )
        # нет переработки
        self._create_worker_day(
            self.employment3,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa2.id,
        )
        # переработка 1 час
        self.wd = self._create_worker_day(
            self.employment4,
            dttm_work_start=datetime.combine(self.dt, time(7)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa3.id,
        )
        self.client.force_authenticate(self.user1)

    def _create_worker_day(self, employment, dt=None, is_fact=False, is_approved=False, dttm_work_start=None, dttm_work_end=None, type_id=WorkerDay.TYPE_WORKDAY, closest_plan_approved_id=None):
        if not dt:
            dt = self.dt
        return WorkerDay.objects.create(
            shop_id=self.shop.id,
            type_id=type_id,
            employment=employment,
            employee=employment.employee,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_fact=is_fact,
            is_approved=is_approved,
            created_by=self.user1,
            closest_plan_approved_id=closest_plan_approved_id,
        )

    def test_get_list(self):
        dt = Converter.convert_date(self.dt)

        response = self.client.get(f'/rest_api/worker_day/?shop_id={self.shop.id}&dt={dt}&is_fact=1')
        self.assertEquals(len(response.json()), 3)
        overtimes = list(map(lambda x: (x['employee_id'], x['unaccounted_overtime']), response.json()))
        assert_overtimes = [
            (self.employee2.id, 180.0),
            (self.employee3.id, 0.0),
            (self.employee4.id, 90.0),
        ]
        self.assertEquals(overtimes, assert_overtimes)

    def test_get(self):
        dt = Converter.convert_date(self.dt)

        response = self.client.get(f'/rest_api/worker_day/{self.wd.id}/')
        self.assertEquals(response.json()['unaccounted_overtime'], 90.0)
