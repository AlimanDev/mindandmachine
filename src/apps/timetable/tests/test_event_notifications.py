from datetime import datetime, timedelta, time
from unittest import mock
import pandas as pd

from django_celery_beat.models import CrontabSchedule
from django.core import mail
from django.db import transaction
from rest_framework import status
from rest_framework.test import APITestCase

from src.apps.base.models import FunctionGroup
from src.apps.base.tests import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
)
from src.apps.events.models import EventType, EventHistory
from src.apps.reports.models import ReportConfig, ReportType, Period
from src.apps.notifications.models import EventEmailNotification
from src.apps.timetable.events import REQUEST_APPROVE_EVENT_TYPE, REQUEST_APPROVE_WITH_TASKS_EVENT_TYPE, APPROVE_EVENT_TYPE, VACANCY_CREATED
from src.apps.reports.reports import OVERTIMES_UNDERTIMES, UNACCOUNTED_OVERTIME
from src.apps.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkerDayPermission, GroupWorkerDayPermission
from src.apps.timetable.tests.factories import WorkerDayCashboxDetailsFactory, WorkerDayFactory
from src.common.mixins.tests import TestsHelperMixin
from src.common.models_converter import Converter
from src.apps.reports.tasks import cron_report
from src.apps.tasks.models import Task
from src.apps.forecast.models import OperationType, OperationTypeName


@mock.patch.object(transaction, 'on_commit', lambda t: t())
class TestRequestApproveEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
        )
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.request_approve_event, _created = EventType.objects.get_or_create(
            code=REQUEST_APPROVE_EVENT_TYPE, network=cls.network)
        FunctionGroup.objects.create(
            group=cls.group_dir,
            method='POST',
            func='WorkerDay_request_approve',
        )
        cls.dt_now = datetime.now().date()

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_request_approve_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Запрос на подтверждение графика'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.request_approve_event,
                shop_ancestors=True,
                system_email_template='notifications/email/request_approve.html',
                subject=subject,
            )
            event_email_notification.shop_groups.add(self.group_urs)
            resp = self.client.post(self.get_url('WorkerDay-request-approve'), data={
                'shop_id': self.shop.id,
                'is_fact': True,
                'dt_from': Converter.convert_date(self.dt_now),
                'dt_to': Converter.convert_date(self.dt_now),
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_urs.email)

    def test_request_approve_with_tasks(self):
        """If `network.request_approve_with_tasks_check` is `True` and
        there are Tasks assigned to employee - create an Event with different code."""
        wd = WorkerDayFactory(
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=False,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(9)),
            dttm_work_end=datetime.combine(self.dt_now, time(13)),
            shop=self.shop
        )
        Task.objects.create(
            employee=wd.employee,
            dttm_start_time=datetime.combine(self.dt_now, time(14)),  # outside work hours
            dttm_end_time=datetime.combine(self.dt_now, time(15)),
            operation_type=OperationType.objects.create(
                operation_type_name=OperationTypeName.objects.create(
                    name='OTN',
                    network=self.network
                )
            )
        )
        resp = self.client.post(self.get_url('WorkerDay-request-approve'), data={
            'shop_id': self.shop.id,
            'is_fact': True,
            'dt_from': Converter.convert_date(self.dt_now),
            'dt_to': Converter.convert_date(self.dt_now),
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(EventHistory.objects.filter(event_type__code=REQUEST_APPROVE_WITH_TASKS_EVENT_TYPE).exists())
        
        self.network.request_approve_with_tasks_check = True
        self.network.save()
        resp = self.client.post(self.get_url('WorkerDay-request-approve'), data={
            'shop_id': self.shop.id,
            'is_fact': True,
            'dt_from': Converter.convert_date(self.dt_now),
            'dt_to': Converter.convert_date(self.dt_now),
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(EventHistory.objects.filter(event_type__code=REQUEST_APPROVE_WITH_TASKS_EVENT_TYPE).exists())


class TestApproveEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop = ShopFactory(parent=cls.root_shop, network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_dir.subordinates.add(cls.group_dir)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_urs.subordinates.add(cls.group_urs)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.group_dir.subordinates.add(cls.group_worker)
        cls.group_urs.subordinates.add(cls.group_worker)
        FunctionGroup.objects.create(group=cls.group_dir, func='WorkerDay_approve', method='POST')
        GroupWorkerDayPermission.objects.create(
            group=cls.group_dir,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
        )
        FunctionGroup.objects.create(group=cls.group_urs, func='WorkerDay_approve', method='POST')
        GroupWorkerDayPermission.objects.create(
            group=cls.group_urs,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.MY_NETWORK_EMPLOYEE
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.approve_event_type, _created = EventType.objects.get_or_create(code=APPROVE_EVENT_TYPE, network=cls.network)
        cls.dt = datetime.now().date()
        cls.plan_not_approved = WorkerDayFactory(
            is_approved=False,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_urs)

    def test_approve_notification_sent_to_director(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'График в магазине {{ shop.name }} был подтвержден'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.approve_event_type,
                system_email_template='notifications/email/request_approve.html',
                subject=subject,
            )
            event_email_notification.shop_groups.add(self.group_dir)
            approve_data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt,
                'dt_to': self.dt,
                'is_fact': False,
                'wd_types': [
                    WorkerDay.TYPE_WORKDAY,
                ],
            }
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-approve'), data=approve_data)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, 'График в магазине {} был подтвержден'.format(self.shop.name))
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)

    def test_approve_notification_not_sent_to_event_author(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            self.client.force_authenticate(user=self.user_dir)
            subject = 'График в магазине {{ shop.name }} был подтвержден'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.approve_event_type,
                system_email_template='notifications/email/request_approve.html',
                subject=subject,
            )
            event_email_notification.shop_groups.add(self.group_dir)
            approve_data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt,
                'dt_to': self.dt,
                'is_fact': False,
                'wd_types': [
                    WorkerDay.TYPE_WORKDAY,
                ],
            }
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-approve'), data=approve_data)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 0)


class TestSendUnaccountedReport(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(only_fact_hours_that_in_approved_plan=True)
        cls.network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'I': 'объект',
                    'R': 'объекта',
                    'P': 'объекте',
                }
            }
        )
        cls.network.save()
        cls.period = Period.objects.create()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
        )
        cls.shop2 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME2',
            network=cls.network,
            email=None,
        )
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.user_worker2 = UserFactory(email='worker2@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        cls.employment_worker2 = EmploymentFactory(
            employee=cls.employee_worker2, shop=cls.shop2, function_group=cls.group_worker,
        )
        cls.unaccounted_overtime_report, _created = ReportType.objects.get_or_create(
            code=UNACCOUNTED_OVERTIME, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        cls.plan_approved = cls._create_worker_day(cls.employment_worker, datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(14)), shop_id=cls.shop.id)
        cls.plan_approved_dir = cls._create_worker_day(cls.employment_dir, datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(16)), shop_id=cls.shop.id)
        cls.plan_approved2 = cls._create_worker_day(cls.employment_worker2, datetime.combine(cls.dt, time(15)), datetime.combine(cls.dt, time(20)), shop_id=cls.shop2.id)
        cls.fact_approved = cls._create_worker_day(cls.employment_worker, datetime.combine(cls.dt, time(7)), datetime.combine(cls.dt, time(13)), is_fact=True, shop_id=cls.shop.id, closest_plan_approved_id=cls.plan_approved.id)
        cls.fact_approved_dir = cls._create_worker_day(cls.employment_dir, datetime.combine(cls.dt, time(7)), datetime.combine(cls.dt, time(19)), is_fact=True, shop_id=cls.shop.id, closest_plan_approved_id=cls.plan_approved_dir.id)
        cls.fact_approved2 = cls._create_worker_day(cls.employment_worker2, datetime.combine(cls.dt, time(14)), datetime.combine(cls.dt, time(20)), is_fact=True, shop_id=cls.shop2.id, closest_plan_approved_id=cls.plan_approved2.id)

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_unaccounted_overtime_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет по неучтенным переработкам'
            report_config = ReportConfig.objects.create(
                report_type=self.unaccounted_overtime_report,
                period=self.period,
                subject=subject,
                email_text='Отчет по неучтенным переработкам',
                cron=self.cron,
                name='Test',
            )
            report_config.users.add(self.user_dir)
            report_config.users.add(self.user_urs)
            report_config.shops_to_notify.add(self.shop)
            
            cron_report()
            
            self.assertEqual(len(mail.outbox), 3)
            self.assertEqual(mail.outbox[0].subject, subject)
            emails = sorted(
                [
                    outbox.to[0]
                    for outbox in mail.outbox
                ]
            )
            self.assertEqual(emails, [self.user_dir.email, self.shop.email, self.user_urs.email])
            df = pd.read_excel(mail.outbox[0].attachments[0][1]).fillna('')
            data = [
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_dir.shop.code, 
                    'Название объекта': self.employment_dir.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_dir.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 4 часов'
                },
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_worker.shop.code, 
                    'Название объекта': self.employment_worker.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_worker.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 1 часа'
                }, 
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_worker2.shop.code, 
                    'Название объекта': self.employment_worker2.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_worker2.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 1 часа'
                }, 
            ]
            self.assertEqual(df.to_dict('records'), data)
            # проверяем, что УРСу не придет, так как его магазина нет в данных
            report_config.filter_recipients_by_shops_in_data = True
            report_config.save()
            mail.outbox.clear()
            cron_report()
            self.assertEqual(len(mail.outbox), 2)
            self.assertEqual(mail.outbox[0].subject, subject)
            emails = sorted(
                [
                    outbox.to[0]
                    for outbox in mail.outbox
                ]
            )
            self.assertEqual(emails, [self.user_dir.email, self.shop.email])

    def test_urv_violators_email_notification_sent_to_shop(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет по неучтенным переработкам'
            report_config = ReportConfig.objects.create(
                report_type=self.unaccounted_overtime_report,
                period=self.period,
                subject=subject,
                email_text='Отчет по неучтенным переработкам',
                cron=self.cron,
                name='Test',
            )
            report_config.shops.add(self.shop2)
            report_config.users.add(self.user_dir)

            cron_report()

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            df = pd.read_excel(mail.outbox[0].attachments[0][1]).fillna('')
            data = [
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_worker2.shop.code, 
                    'Название объекта': self.employment_worker2.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_worker2.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 1 часа'
                },
            ]
            self.assertEqual(df.to_dict('records'), data)

    def test_unaccounted_overtime_email_notification_sent_by_groups(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет по неучтенным переработкам'
            report_config = ReportConfig.objects.create(
                report_type=self.unaccounted_overtime_report,
                period=self.period,
                subject=subject,
                email_text='Отчет по неучтенным переработкам',
                cron=self.cron,
                name='Test',
                send_by_group_employments_shops=True,
            )
            report_config.groups.add(self.group_urs)

            root_shop2 = ShopFactory(name='Root_Shop2', network=self.network)
            shop = ShopFactory(
                parent=root_shop2,
                name='SHOP_NAME3',
                network=self.network,
                email='shop3@example.com',
            )
            user_dir = UserFactory(email='dir2@example.com', network=self.network)
            employee_dir = EmployeeFactory(user=user_dir)
            user_urs = UserFactory(email='urs2@example.com', network=self.network)
            employee_urs = EmployeeFactory(user=user_urs)
            user_worker = UserFactory(email='worker2@example.com', network=self.network)
            employee_worker = EmployeeFactory(user=user_worker)
            employment_dir = EmploymentFactory(
                employee=employee_dir, shop=shop, function_group=self.group_dir,
            )
            employment_urs = EmploymentFactory(
                employee=employee_urs, shop=root_shop2, function_group=self.group_urs,
            )
            employment_worker = EmploymentFactory(
                employee=employee_worker, shop=shop, function_group=self.group_worker,
            )
            pa1 = self._create_worker_day(employment_worker, datetime.combine(self.dt, time(8)), datetime.combine(self.dt, time(14)), shop_id=shop.id)
            pa2 = self._create_worker_day(employment_dir, datetime.combine(self.dt, time(8)), datetime.combine(self.dt, time(16)), shop_id=shop.id)
            self._create_worker_day(employment_worker, datetime.combine(self.dt, time(7)), datetime.combine(self.dt, time(15)), is_fact=True, shop_id=shop.id, closest_plan_approved_id=pa1.id)
            self._create_worker_day(employment_dir, datetime.combine(self.dt, time(8)), datetime.combine(self.dt, time(19)), is_fact=True, shop_id=shop.id, closest_plan_approved_id=pa2.id)

            cron_report()

            self.assertEqual(len(mail.outbox), 2)
            self.assertEqual(mail.outbox[0].subject, subject)
            mails_by_emails = {
                outbox.to[0]: outbox
                for outbox in mail.outbox
            }
            self.assertCountEqual(list(mails_by_emails.keys()), [user_urs.email, self.user_urs.email])
            df1 = pd.read_excel(mails_by_emails[user_urs.email].attachments[0][1]).fillna('')
            df2 = pd.read_excel(mails_by_emails[self.user_urs.email].attachments[0][1]).fillna('')
            self.assertNotEqual(df1.to_dict('records'), df2.to_dict('records'))
            data1 = [
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': employment_dir.shop.code, 
                    'Название объекта': employment_dir.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': employment_dir.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 3 часов'
                },
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': employment_worker.shop.code, 
                    'Название объекта': employment_worker.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': employment_worker.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 2 часов'
                }, 
            ]
            data2 = [
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_dir.shop.code, 
                    'Название объекта': self.employment_dir.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_dir.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 4 часов'
                },
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_worker.shop.code, 
                    'Название объекта': self.employment_worker.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_worker.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 1 часа'
                }, 
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'), 
                    'Код объекта': self.employment_worker2.shop.code, 
                    'Название объекта': self.employment_worker2.shop.name, 
                    'Табельный номер': '', 
                    'ФИО': self.employment_worker2.employee.user.get_fio(), 
                    'Неучтенные переработки': 'более 1 часа'
                }, 
            ]
            self.assertEqual(df1.to_dict('records'), data1)
            self.assertEqual(df2.to_dict('records'), data2)


class TestOvertimesUndertimesReport(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(only_fact_hours_that_in_approved_plan=True)
        cls.period = Period.objects.create()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
        )
        cls.shop2 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME2',
            network=cls.network,
            email=None,
        )
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.user_worker2 = UserFactory(email='worker2@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        cls.employment_worker2 = EmploymentFactory(
            employee=cls.employee_worker2, shop=cls.shop2, function_group=cls.group_worker,
        )
        cls.overtimes_undertimes_report, _created = ReportType.objects.get_or_create(
            code=OVERTIMES_UNDERTIMES, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        cls.plan_approved = cls._create_worker_day(cls.employment_worker, datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(14)), shop_id=cls.shop.id)
        cls.plan_approved_dir = cls._create_worker_day(cls.employment_dir, datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(16)), shop_id=cls.shop.id)
        cls.plan_approved2 = cls._create_worker_day(cls.employment_worker2, datetime.combine(cls.dt, time(15)), datetime.combine(cls.dt, time(20)), shop_id=cls.shop2.id)
        cls.fact_approved = cls._create_worker_day(cls.employment_worker, datetime.combine(cls.dt, time(7)), datetime.combine(cls.dt, time(13)), is_fact=True, shop_id=cls.shop.id)
        cls.fact_approved_dir = cls._create_worker_day(cls.employment_dir, datetime.combine(cls.dt, time(7)), datetime.combine(cls.dt, time(19)), is_fact=True, shop_id=cls.shop.id)
        cls.fact_approved2 = cls._create_worker_day(cls.employment_worker2, datetime.combine(cls.dt, time(14)), datetime.combine(cls.dt, time(20)), is_fact=True, shop_id=cls.shop2.id)


    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_overtimes_undertimes_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет по переработкам/недоработкам'
            report_config = ReportConfig.objects.create(
                report_type=self.overtimes_undertimes_report,
                period=self.period,
                subject=subject,
                email_text='Отчет по переработкам/недоработкам',
                cron=self.cron,
                name='Test',
            )
            report_config.users.add(self.user_dir)
            report_config.users.add(self.user_urs)
            report_config.shops_to_notify.add(self.shop)
            
            cron_report()
            
            self.assertEqual(len(mail.outbox), 3)
            self.assertEqual(mail.outbox[0].subject, subject)
            emails = sorted(
                [
                    outbox.to[0]
                    for outbox in mail.outbox
                ]
            )
            self.assertEqual(emails, [self.user_dir.email, self.shop.email, self.user_urs.email])
            df = pd.read_excel(mail.outbox[0].attachments[0][1]).fillna('')
            self.assertEqual(len(df.to_dict('records')), 11)


class TestVacancyCreatedNotification(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(name='Client', code='client')
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
        cls.outsource_network = NetworkFactory(name='Outsource', code='outsource')
        cls.outsource_network2 = NetworkFactory(name='Outsource2', code='outsource2')
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
        )
        cls.shop2 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME2',
            network=cls.network,
            email=None,
        )
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.user_worker2 = UserFactory(email='worker2@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_dir.subordinates.add(cls.group_dir)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.group_dir.subordinates.add(cls.group_worker)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        cls.employment_worker2 = EmploymentFactory(
            employee=cls.employee_worker2, shop=cls.shop2, function_group=cls.group_worker,
        )
        cls.vacancy_created_event, _created = EventType.objects.get_or_create(
            code=VACANCY_CREATED, network=cls.network)

        cls.user_outsource = UserFactory(email='outsource@example.com', network=cls.outsource_network)
        cls.user_outsource2 = UserFactory(email='outsource2@example.com', network=cls.outsource_network2)

        FunctionGroup.objects.create(group=cls.group_dir, func='WorkerDay_approve', method='POST')
        FunctionGroup.objects.create(group=cls.group_dir, func='WorkerDay_approve_vacancy', method='POST')
        GroupWorkerDayPermission.objects.create(
            group=cls.group_dir,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type=WorkerDay.TYPE_WORKDAY,
            ),
        )
        GroupWorkerDayPermission.objects.create(
            group=cls.group_dir,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.DELETE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type=WorkerDay.TYPE_WORKDAY,
            ),
        )
        cls.dt = datetime.now().date()
        cls.not_approved_plan = cls._create_worker_day(cls.employment_worker, datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(14)), shop_id=cls.shop.id, is_approved=False)
        cls.not_approved_vacancy = cls._create_worker_day(
            None,
            datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(14)), shop_id=cls.shop.id, is_approved=False, outsources=[cls.outsource_network], is_vacancy=True,
        )
        cls.not_approved_vacancy_with_employee = cls._create_worker_day(
            cls.employment_dir,
            datetime.combine(cls.dt, time(8)), datetime.combine(cls.dt, time(14)), shop_id=cls.shop.id, is_approved=False, outsources=[cls.outsource_network], is_vacancy=True,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_vacancy_created_notification_sent_on_approve(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Создана новая вакансия'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.vacancy_created_event,
                system_email_template='notifications/email/vacancy_created.html',
                subject=subject,
            )
            event_email_notification.users.add(self.user_outsource)
            event_email_notification.users.add(self.user_outsource2)
            approve_data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt,
                'dt_to': self.dt,
                'is_fact': False,
                'wd_types': [
                    WorkerDay.TYPE_WORKDAY,
                ],
                'approve_open_vacs': True,
            }
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-approve'), data=approve_data)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, 'Создана новая вакансия')
            self.assertEqual(mail.outbox[0].to[0], self.user_outsource.email)
            dttm_from = self.not_approved_vacancy.dttm_work_start.strftime('%Y-%m-%d %H:%M:%S')
            dttm_to = self.not_approved_vacancy.dttm_work_end.strftime('%Y-%m-%d %H:%M:%S')
            self.assertEqual(
                mail.outbox[0].body, 
                f'Здравствуйте, {self.user_outsource.first_name}!\n\n\n\n\n\n\nВ подразделении {self.shop.name} создана вакансия для типа работ Работа\n'
                f'Дата: {self.dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
            )

    def test_vacancy_created_notification_sent_on_approve_vacancy(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Создана новая вакансия'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.vacancy_created_event,
                system_email_template='notifications/email/vacancy_created.html',
                subject=subject,
            )
            event_email_notification.users.add(self.user_outsource)
            event_email_notification.users.add(self.user_outsource2)
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-approve-vacancy', pk=self.not_approved_vacancy.id))
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, 'Создана новая вакансия')
            self.assertEqual(mail.outbox[0].to[0], self.user_outsource.email)
            dttm_from = self.not_approved_vacancy.dttm_work_start.strftime('%Y-%m-%d %H:%M:%S')
            dttm_to = self.not_approved_vacancy.dttm_work_end.strftime('%Y-%m-%d %H:%M:%S')
            self.assertEqual(
                mail.outbox[0].body, 
                f'Здравствуйте, {self.user_outsource.first_name}!\n\n\n\n\n\n\nВ подразделении {self.shop.name} создана вакансия для типа работ Работа\n'
                f'Дата: {self.dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
            )

    def test_vacancy_created_notification_sent_on_approve_vacancy_many_work_types(self):
        WorkerDayCashboxDetailsFactory(
            worker_day=self.not_approved_vacancy,
            work_type__work_type_name__name='Касса',
        )
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Создана новая вакансия'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.vacancy_created_event,
                system_email_template='notifications/email/vacancy_created.html',
                subject=subject,
            )
            event_email_notification.users.add(self.user_outsource)
            event_email_notification.users.add(self.user_outsource2)
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-approve-vacancy', pk=self.not_approved_vacancy.id))
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, 'Создана новая вакансия')
            self.assertEqual(mail.outbox[0].to[0], self.user_outsource.email)
            dttm_from = self.not_approved_vacancy.dttm_work_start.strftime('%Y-%m-%d %H:%M:%S')
            dttm_to = self.not_approved_vacancy.dttm_work_end.strftime('%Y-%m-%d %H:%M:%S')
            work_types = ', '.join(
                WorkerDayCashboxDetails.objects.filter(
                    worker_day=self.not_approved_vacancy,
                ).select_related(
                    'work_type__work_type_name',
                ).values_list('work_type__work_type_name__name', flat=True)
            )
            
            self.assertEqual(
                mail.outbox[0].body, 
                f'Здравствуйте, {self.user_outsource.first_name}!\n\n\n\n\n\n\nВ подразделении {self.shop.name} создана вакансия для типов работ {work_types}\n'
                f'Дата: {self.dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
            )

    def test_vacancy_created_notification_not_sent_on_approve(self):
        WorkerDay.objects.filter(is_vacancy=True).update(is_approved=True)
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Создана новая вакансия'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.vacancy_created_event,
                system_email_template='notifications/email/vacancy_created.html',
                subject=subject,
            )
            event_email_notification.users.add(self.user_outsource)
            event_email_notification.users.add(self.user_outsource2)
            approve_data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt,
                'dt_to': self.dt,
                'is_fact': False,
                'wd_types': [
                    WorkerDay.TYPE_WORKDAY,
                ],
            }
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-approve'), data=approve_data)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 0)
