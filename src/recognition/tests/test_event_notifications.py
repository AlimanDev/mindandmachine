from datetime import datetime, timedelta, time
import pandas as pd

from django.core import mail
from rest_framework import status
from rest_framework.test import APITestCase
from django_celery_beat.models import CrontabSchedule

from src.base.models import FunctionGroup
from src.base.tests.factories import ShopFactory, UserFactory, GroupFactory, EmploymentFactory, NetworkFactory
from src.events.models import EventType
from src.notifications.models import EventEmailNotification
from src.recognition.events import URV_STAT, URV_STAT_TODAY, URV_VIOLATORS_REPORT, URV_STAT_V2
from src.timetable.models import WorkerDay, AttendanceRecords
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.celery.tasks import cron_event
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
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir, network=cls.network
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs, network=cls.network
        )
        cls.employment_worker = EmploymentFactory(
            user=cls.user_worker, shop=cls.shop, function_group=cls.group_worker, network=cls.network
        )
        cls.urv_stat_event, _created = EventType.objects.get_or_create(
            code=URV_STAT, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            worker=cls.user_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_stat_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.urv_stat_event,
                subject=subject,
                custom_email_template='Отчет УРВ',
                cron=self.cron,
            )
            event_email_notification.users.add(self.user_dir)
            event_email_notification.users.add(self.user_urs)
            event_email_notification.shops.add(self.shop)
            
            cron_event()
            
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
            data = {
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
            }
            self.assertEqual(dict(df.iloc[0]), data)


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
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir, network=cls.network
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs, network=cls.network
        )
        cls.employment_worker = EmploymentFactory(
            user=cls.user_worker, shop=cls.shop, function_group=cls.group_worker, network=cls.network
        )
        cls.urv_stat_event, _created = EventType.objects.get_or_create(
            code=URV_STAT_TODAY, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date()
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            worker=cls.user_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_stat_today_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ за сегодня'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.urv_stat_event,
                subject=subject,
                custom_email_template='Отчет УРВ за сегодня',
                cron=self.cron,
            )
            event_email_notification.users.add(self.user_dir)
            event_email_notification.users.add(self.user_urs)
            event_email_notification.shops.add(self.shop)
            
            cron_event()
            
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
            data = {
                'Магазин': 'SHOP_NAME', 
                'Дата': self.dt.strftime('%d.%m.%Y'), 
                'Кол-во отметок план, ПРИХОД': 1, 
                'Кол-во отметок факт, ПРИХОД': 0, 
                'Разница, ПРИХОД': 1, 
            }
            self.assertEqual(dict(df.iloc[0]), data)


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
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir, network=cls.network
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs, network=cls.network
        )
        cls.employment_worker = EmploymentFactory(
            user=cls.user_worker, shop=cls.shop, function_group=cls.group_worker, network=cls.network
        )
        cls.urv_violators_event, _created = EventType.objects.get_or_create(
            code=URV_VIOLATORS_REPORT, network=cls.network)
        
        cls.cron = CrontabSchedule.objects.create()
        cls.dt = datetime.now().date() - timedelta(1)
        cls.plan_approved = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            worker=cls.user_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
        )
        cls.plan_approved_dir = WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_dir,
            worker=cls.user_dir,
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
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.urv_violators_event,
                subject=subject,
                custom_email_template='Отчет о нарушителях УРВ',
                cron=self.cron,
            )
            event_email_notification.users.add(self.user_dir)
            event_email_notification.users.add(self.user_urs)
            event_email_notification.shops.add(self.shop)
            
            cron_event()
            
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
                    'Код объекта': self.shop.code,
                    'Название объекта': self.shop.name,
                    'Табельный номер': '',  
                    'ФИО': f'{self.user_dir.last_name} {self.user_dir.first_name} {self.user_dir.middle_name}', 
                    'Нарушение': 'Нет ухода',
                }, 
                {
                    'Код объекта': self.shop.code,
                    'Название объекта': self.shop.name, 
                    'Табельный номер': '',
                    'ФИО': f'{self.user_worker.last_name} {self.user_worker.first_name} {self.user_worker.middle_name}', 
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
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir, network=cls.network
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs, network=cls.network
        )
        cls.employment_worker = EmploymentFactory(
            user=cls.user_worker, shop=cls.shop, function_group=cls.group_worker, network=cls.network
        )
        cls.urv_stat_event, _created = EventType.objects.get_or_create(
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

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_urv_stat_email_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Отчет УРВ версия 2'
            event_email_notification = EventEmailNotification.objects.create(
                event_type=self.urv_stat_event,
                subject=subject,
                custom_email_template='Отчет УРВ версия 2',
                cron=self.cron,
            )
            event_email_notification.users.add(self.user_dir)
            event_email_notification.users.add(self.user_urs)
            event_email_notification.shops.add(self.shop)
            
            cron_event()
            
            self.assertEqual(len(mail.outbox), 3)
            self.assertEqual(mail.outbox[0].subject, subject)
            emails = sorted(
                [
                    outbox.to[0]
                    for outbox in mail.outbox
                ]
            )
            self.assertEqual(emails, [self.user_dir.email, self.shop.email, self.user_urs.email])
            df = pd.read_excel(mail.outbox[0].attachments[0][1])
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
            ]
            self.assertEqual(df.to_dict('records'), data)