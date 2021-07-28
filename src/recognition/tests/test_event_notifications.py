from datetime import datetime, timedelta, time
import json
import pandas as pd
from unittest import mock

from django.core import mail
from django.db import transaction
from rest_framework.test import APITestCase
from django_celery_beat.models import CrontabSchedule

from src.base.tests.factories import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
)
from src.events.models import EventType
from src.notifications.models import EventEmailNotification
from src.recognition.events import (
    EMPLOYEE_NOT_CHECKED_IN,
    EMPLOYEE_NOT_CHECKED_OUT,
    EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN,
)
from src.reports.reports import (
    URV_STAT,
    URV_STAT_TODAY, 
    URV_VIOLATORS_REPORT, 
    URV_STAT_V2,
)
from src.reports.models import ReportConfig, ReportType
from src.timetable.models import WorkerDay, AttendanceRecords
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.reports.tasks import cron_report
from src.celery.tasks import employee_not_checked
from xlrd import open_workbook


class TestSendUrvStatEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
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
        cls.urv_stat_report, _created = ReportType.objects.get_or_create(
            code=URV_STAT, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )
        cls.plan_approved2 = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop2,
            employment=cls.employment_worker2,
            employee=cls.employee_worker2,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_stat_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_stat_report,
                subject=subject,
                email_text='Отчет УРВ',
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
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            data = [
                {
                    'Магазин': 'SHOP_NAME',
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Кол-во отметок план, ПРИХОД': 1,
                    'Опоздания': 0,
                    'Ранний уход': 0,
                    'Кол-во отметок факт, ПРИХОД': 0,
                    'Разница, ПРИХОД': 1,
                    'Кол-во отметок план, УХОД': 1,
                    'Кол-во отметок факт, УХОД': 0,
                    'Разница, УХОД': 1,
                    'Кол-во часов план': '08:45:00',
                    'Кол-во часов факт': '00:00:00',
                    'Разница, ЧАСЫ': '08:45:00',
                    'Разница, ПРОЦЕНТЫ': '0%',
                },
                {
                    'Магазин': 'SHOP_NAME2',
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Кол-во отметок план, ПРИХОД': 1,
                    'Опоздания': 0,
                    'Ранний уход': 0,
                    'Кол-во отметок факт, ПРИХОД': 0,
                    'Разница, ПРИХОД': 1,
                    'Кол-во отметок план, УХОД': 1,
                    'Кол-во отметок факт, УХОД': 0,
                    'Разница, УХОД': 1,
                    'Кол-во часов план': '08:45:00',
                    'Кол-во часов факт': '00:00:00',
                    'Разница, ЧАСЫ': '08:45:00',
                    'Разница, ПРОЦЕНТЫ': '0%',
                },
            ]
            self.assertEqual(df.to_dict('records'), data)

    def test_urv_stat_email_notification_sent_to_one_shop(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_stat_report,
                subject=subject,
                email_text='Отчет УРВ',
                cron=self.cron,
                name='Test',
            )
            report_config.shops.add(self.shop2)
            report_config.users.add(self.user_dir)


            cron_report()
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            data = [
                {
                    'Магазин': 'SHOP_NAME2',
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Кол-во отметок план, ПРИХОД': 1,
                    'Опоздания': 0,
                    'Ранний уход': 0,
                    'Кол-во отметок факт, ПРИХОД': 0,
                    'Разница, ПРИХОД': 1,
                    'Кол-во отметок план, УХОД': 1,
                    'Кол-во отметок факт, УХОД': 0,
                    'Разница, УХОД': 1,
                    'Кол-во часов план': '08:45:00',
                    'Кол-во часов факт': '00:00:00',
                    'Разница, ЧАСЫ': '08:45:00',
                    'Разница, ПРОЦЕНТЫ': '0%',
                },
            ]
            self.assertEqual(df.to_dict('records'), data)


class TestSendUrvStatTodayEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
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
        cls.urv_stat_report, _created = ReportType.objects.get_or_create(
            code=URV_STAT_TODAY, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date()
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop2,
            employment=cls.employment_worker2,
            employee=cls.employee_worker2,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_stat_today_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ за сегодня'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_stat_report,
                subject=subject,
                email_text='Отчет УРВ за сегодня',
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
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            data = [
                {
                    'Магазин': 'SHOP_NAME',
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Кол-во отметок план, ПРИХОД': 1,
                    'Кол-во отметок факт, ПРИХОД': 0,
                    'Разница, ПРИХОД': 1,
                },
                {
                    'Магазин': 'SHOP_NAME2',
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Кол-во отметок план, ПРИХОД': 1,
                    'Кол-во отметок факт, ПРИХОД': 0,
                    'Разница, ПРИХОД': 1,
                },
            ]
            self.assertEqual(df.to_dict('records'), data)

    def test_urv_stat_today_email_notification_sent_to_shop(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ за сегодня'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_stat_report,
                subject=subject,
                email_text='Отчет УРВ за сегодня',
                cron=self.cron,
                name='Test',
            )
            report_config.shops.add(self.shop2)
            report_config.users.add(self.user_dir)

            cron_report()

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            data = [
                {
                    'Магазин': 'SHOP_NAME2',
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Кол-во отметок план, ПРИХОД': 1,
                    'Кол-во отметок факт, ПРИХОД': 0,
                    'Разница, ПРИХОД': 1,
                },
            ]
            self.assertEqual(df.to_dict('records'), data)



class TestSendUrvViolatorsEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
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
        cls.urv_violators_report, _created = ReportType.objects.get_or_create(
            code=URV_VIOLATORS_REPORT, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )
        cls.plan_approved_dir = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )
        cls.plan_approved2 = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop2,
            employment=cls.employment_worker2,
            employee=cls.employee_worker2,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )

        AttendanceRecords.objects.create(
            shop=cls.shop,
            type=AttendanceRecords.TYPE_COMING,
            user=cls.user_dir,
            dttm=datetime.combine(cls.dt, time(8))
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_violators_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет о нарушителях УРВ'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_violators_report,
                subject=subject,
                email_text='Отчет о нарушителях УРВ',
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
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd').fillna('')
            data = [
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Код объекта': self.shop.code,
                    'Название объекта': self.shop.name,
                    'Табельный номер': '',  
                    'ФИО': f'{self.user_dir.last_name} {self.user_dir.first_name} {self.user_dir.middle_name}', 
                    'Нарушение': 'Нет ухода',
                }, 
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Код объекта': self.shop.code,
                    'Название объекта': self.shop.name, 
                    'Табельный номер': '',
                    'ФИО': f'{self.user_worker.last_name} {self.user_worker.first_name} {self.user_worker.middle_name}', 
                    'Нарушение': 'Нет отметок',
                },
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Код объекта': self.shop2.code,
                    'Название объекта': self.shop2.name,
                    'Табельный номер': '',
                    'ФИО': f'{self.user_worker2.last_name} {self.user_worker2.first_name} {self.user_worker2.middle_name}',
                    'Нарушение': 'Нет отметок',
                },
            ]
            self.assertEqual(df.to_dict('records'), data)

    def test_urv_violators_email_notification_sent_to_shop(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет о нарушителях УРВ'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_violators_report,
                subject=subject,
                email_text='Отчет о нарушителях УРВ',
                cron=self.cron,
                name='Test',
            )
            report_config.shops.add(self.shop2)
            report_config.users.add(self.user_dir)

            cron_report()

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd').fillna('')
            data = [
                {
                    'Дата': self.dt.strftime('%d.%m.%Y'),
                    'Код объекта': self.shop2.code,
                    'Название объекта': self.shop2.name,
                    'Табельный номер': '',
                    'ФИО': f'{self.user_worker2.last_name} {self.user_worker2.first_name} {self.user_worker2.middle_name}',
                    'Нарушение': 'Нет отметок',
                },
            ]
            self.assertEqual(df.to_dict('records'), data)


class TestSendUrvStatV2EventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
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
        cls.urv_stat_report, _created = ReportType.objects.get_or_create(
            code=URV_STAT_V2, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        AttendanceRecords.objects.create(
            shop=cls.shop,
            type=AttendanceRecords.TYPE_COMING,
            user=cls.user_dir,
            dttm=datetime.combine(cls.dt, time(10, 40))
        )
        AttendanceRecords.objects.create(
            shop=cls.shop,
            type=AttendanceRecords.TYPE_LEAVING,
            user=cls.user_dir,
            dttm=datetime.combine(cls.dt, time(22, 4))
        )
        AttendanceRecords.objects.create(
            shop=cls.shop,
            type=AttendanceRecords.TYPE_COMING,
            user=cls.user_worker,
            dttm=datetime.combine(cls.dt, time(12, 11))
        )
        AttendanceRecords.objects.create(
            shop=cls.shop2,
            type=AttendanceRecords.TYPE_COMING,
            user=cls.user_worker2,
            dttm=datetime.combine(cls.dt, time(10, 28))
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_stat_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ версия 2'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_stat_report,
                subject=subject,
                email_text='Отчет УРВ версия 2',
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
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            data = [
                {
                    'Код магазина': self.shop.code, 
                    'Магазин': 'SHOP_NAME', 
                    'Время события': datetime.combine(self.dt, time(10, 40)).strftime('%Y-%m-%d %H:%M:%S'), 
                    'Табельный номер сотрудника': 'Без табельного номера', 
                    'ФИО сотрудника': f'{self.user_dir.last_name} {self.user_dir.first_name} {self.user_dir.middle_name}', 
                    'Тип события': 'Приход',
                }, 
                {
                    'Код магазина': self.shop.code, 
                    'Магазин': 'SHOP_NAME', 
                    'Время события': datetime.combine(self.dt, time(12, 11)).strftime('%Y-%m-%d %H:%M:%S'), 
                    'Табельный номер сотрудника': 'Без табельного номера', 
                    'ФИО сотрудника': f'{self.user_worker.last_name} {self.user_worker.first_name} {self.user_worker.middle_name}', 
                    'Тип события': 'Приход',
                }, 
                {
                    'Код магазина': self.shop.code, 
                    'Магазин': 'SHOP_NAME', 
                    'Время события': datetime.combine(self.dt, time(22, 4)).strftime('%Y-%m-%d %H:%M:%S'), 
                    'Табельный номер сотрудника': 'Без табельного номера', 
                    'ФИО сотрудника': f'{self.user_dir.last_name} {self.user_dir.first_name} {self.user_dir.middle_name}', 
                    'Тип события': 'Уход',
                }, 
                {
                    'Код магазина': self.shop2.code,
                    'Магазин': 'SHOP_NAME2',
                    'Время события': datetime.combine(self.dt, time(10, 28)).strftime('%Y-%m-%d %H:%M:%S'),
                    'Табельный номер сотрудника': 'Без табельного номера',
                    'ФИО сотрудника': f'{self.user_worker2.last_name} {self.user_worker2.first_name} {self.user_worker2.middle_name}',
                    'Тип события': 'Приход',
                },
            ]
            self.assertEqual(df.to_dict('records'), data)

    def test_urv_stat_email_notification_sent_to_shop(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ версия 2'
            report_config = ReportConfig.objects.create(
                report_type=self.urv_stat_report,
                subject=subject,
                email_text='Отчет УРВ версия 2',
                cron=self.cron,
                name='Test',
            )
            report_config.shops.add(self.shop2)
            report_config.users.add(self.user_dir)

            cron_report()

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            data = [
                {
                    'Код магазина': self.shop2.code,
                    'Магазин': 'SHOP_NAME2',
                    'Время события': datetime.combine(self.dt, time(10, 28)).strftime('%Y-%m-%d %H:%M:%S'),
                    'Табельный номер сотрудника': 'Без табельного номера',
                    'ФИО сотрудника': f'{self.user_worker2.last_name} {self.user_worker2.first_name} {self.user_worker2.middle_name}',
                    'Тип события': 'Приход',
                },
            ]
            self.assertEqual(df.to_dict('records'), data)


class TestEmployeeNotCheckedEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
            director=cls.user_dir,
        )
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
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
        cls.event_in, _created = EventType.objects.get_or_create(
            code=EMPLOYEE_NOT_CHECKED_IN, network=cls.network)

        cls.event_out, _created = EventType.objects.get_or_create(
            code=EMPLOYEE_NOT_CHECKED_OUT, network=cls.network)
        
        cls.dt = datetime.now().date()
        cls.now = datetime.now() + timedelta(hours=cls.shop.get_tz_offset())
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=cls.now - timedelta(minutes=5),
            dttm_work_end=cls.now + timedelta(hours=6),
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=cls.now - timedelta(hours=6),
            dttm_work_end=cls.now - timedelta(minutes=5),
        )
        AttendanceRecords.objects.create(
            shop=cls.shop,
            type=AttendanceRecords.TYPE_COMING,
            user=cls.user_dir,
            dttm=cls.now - timedelta(hours=6, minutes=23)
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_employee_not_checked_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject_in = 'Сотрудник не отметился на приход'
            EventEmailNotification.objects.create(
                event_type=self.event_in,
                subject=subject_in,
                system_email_template='notifications/email/employee_not_checked.html',
                get_recipients_from_event_type=True,
            )
            subject_out = 'Сотрудник не отметился на уход'
            EventEmailNotification.objects.create(
                event_type=self.event_out,
                subject=subject_out,
                system_email_template='notifications/email/employee_not_checked.html',
                get_recipients_from_event_type=True,
            )
            
            employee_not_checked()
            
            self.assertEqual(len(mail.outbox), 2)
            self.assertEqual(mail.outbox[0].subject, subject_in)
            self.assertEqual(mail.outbox[1].subject, subject_out)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            dttm = (self.now - timedelta(minutes=5)).replace(second=0).strftime('%Y-%m-%d %H:%M:%S')
            body1 = f'Здравствуйте, {self.user_dir.first_name}!\n\nСотрудник {self.user_worker.last_name} {self.user_worker.first_name} не отметился на приход в {dttm}.\n\nПисьмо отправлено роботом.'
            self.assertEqual(mail.outbox[0].body, body1)
            body2 = f'Здравствуйте, {self.user_dir.first_name}!\n\nСотрудник {self.user_dir.last_name} {self.user_dir.first_name} не отметился на уход в {dttm}.\n\nПисьмо отправлено роботом.'
            self.assertEqual(mail.outbox[1].body, body2)

    
    def test_employee_not_checked_notification_sent_only_one(self):
        AttendanceRecords.objects.create(
            shop=self.shop,
            type=AttendanceRecords.TYPE_LEAVING,
            user=self.user_dir,
            dttm=self.now,
        )
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject_in = 'Сотрудник не отметился на приход'
            EventEmailNotification.objects.create(
                event_type=self.event_in,
                subject=subject_in,
                system_email_template='notifications/email/employee_not_checked.html',
                get_recipients_from_event_type=True,
            )
            subject_out = 'Сотрудник не отметился на уход'
            EventEmailNotification.objects.create(
                event_type=self.event_out,
                subject=subject_out,
                system_email_template='notifications/email/employee_not_checked.html',
                get_recipients_from_event_type=True,
            )
            
            employee_not_checked()
            
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject_in)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            dttm = (self.now - timedelta(minutes=5)).replace(second=0).strftime('%Y-%m-%d %H:%M:%S')
            body1 = f'Здравствуйте, {self.user_dir.first_name}!\n\nСотрудник {self.user_worker.last_name} {self.user_worker.first_name} не отметился на приход в {dttm}.\n\nПисьмо отправлено роботом.'
            self.assertEqual(mail.outbox[0].body, body1)

    def test_employee_not_checked_notification_sent_custom_deltas(self):
        self.network.settings_values = json.dumps(
            {
                'delta_for_comming_in_secs': 120,
                'delta_for_leaving_in_secs': 240,
            }
        )
        self.network.save()
        WorkerDay.objects.filter(
            employee=self.employee_worker,
        ).update(
            dttm_work_start=self.now - timedelta(minutes=2),
        )
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject_in = 'Сотрудник не отметился на приход'
            EventEmailNotification.objects.create(
                event_type=self.event_in,
                subject=subject_in,
                system_email_template='notifications/email/employee_not_checked.html',
                get_recipients_from_event_type=True,
            )
            subject_out = 'Сотрудник не отметился на уход'
            EventEmailNotification.objects.create(
                event_type=self.event_out,
                subject=subject_out,
                system_email_template='notifications/email/employee_not_checked.html',
                get_recipients_from_event_type=True,
            )
            
            employee_not_checked()
            
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject_in)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            dttm = (self.now - timedelta(minutes=2)).replace(second=0).strftime('%Y-%m-%d %H:%M:%S')
            body1 = f'Здравствуйте, {self.user_dir.first_name}!\n\nСотрудник {self.user_worker.last_name} {self.user_worker.first_name} не отметился на приход в {dttm}.\n\nПисьмо отправлено роботом.'
            self.assertEqual(mail.outbox[0].body, body1)


class TestEmployeeWorkingNotAccordingToPlanEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
            director=cls.user_dir,
        )
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
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
        cls.event, _created = EventType.objects.get_or_create(
            code=EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN, network=cls.network)
        
        cls.dt = datetime.now().date()
        cls.now = datetime.now() + timedelta(hours=cls.shop.get_tz_offset())
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_employee_working_not_according_to_plan_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()): 
                subject = 'Сотрудник вышел не по плану'
                event_email_notification = EventEmailNotification.objects.create(
                    event_type=self.event,
                    subject=subject,
                    system_email_template='notifications/email/employee_working_not_according_to_plan.html',
                    get_recipients_from_event_type=True,
                )
                AttendanceRecords.objects.create(
                    shop=self.shop,
                    type=AttendanceRecords.TYPE_COMING,
                    dttm=datetime.combine(self.dt, time(7, 50)),
                    user=self.user_dir,
                )
                AttendanceRecords.objects.create(
                    shop=self.shop,
                    type=AttendanceRecords.TYPE_COMING,
                    dttm=datetime.combine(self.dt, time(9, 3)),
                    user=self.user_worker,
                )
                AttendanceRecords.objects.create(
                    shop=self.shop,
                    type=AttendanceRecords.TYPE_LEAVING,
                    dttm=datetime.combine(self.dt, time(21, 34)),
                    user=self.user_worker,
                )
            
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
            dttm = datetime.combine(self.dt, time(9, 3)).strftime('%Y-%m-%d %H:%M:%S')
            body = f'Здравствуйте, {self.user_dir.first_name}!\n\nСотрудник {self.user_worker.last_name} {self.user_worker.first_name} вышел не по плану в {dttm}.\n\nПисьмо отправлено роботом.'
            self.assertEqual(mail.outbox[0].body, body)
