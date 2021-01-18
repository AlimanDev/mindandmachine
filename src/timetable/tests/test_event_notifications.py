from datetime import datetime
from unittest import mock

from django.core import mail
from django.db import transaction
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import FunctionGroup
from src.base.tests.factories import ShopFactory, UserFactory, GroupFactory, EmploymentFactory, NetworkFactory
from src.events.models import EventType
from src.notifications.models import EventEmailNotification
from src.timetable.events import REQUEST_APPROVE_EVENT_TYPE, APPROVE_EVENT_TYPE
from src.timetable.models import WorkerDay, WorkerDayPermission, GroupWorkerDayPermission
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


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
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        FunctionGroup.objects.create(group=cls.group_dir, func='WorkerDay_request_approve', method='POST')
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir, network=cls.network
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs, network=cls.network
        )
        cls.request_approve_event, _created = EventType.objects.get_or_create(
            code=REQUEST_APPROVE_EVENT_TYPE, network=cls.network)

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
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                resp = self.client.post(self.get_url('WorkerDay-request-approve'), data={'shop_id': self.shop.id})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, subject)
            self.assertEqual(mail.outbox[0].to[0], self.user_urs.email)


class TestApproveEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop = ShopFactory(parent=cls.root_shop, network=cls.network)
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        FunctionGroup.objects.create(group=cls.group_urs, func='WorkerDay_approve', method='POST')
        GroupWorkerDayPermission.objects.create(
            group=cls.group_urs,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type=WorkerDay.TYPE_WORKDAY,
            ),
        )
        cls.employment_worker = EmploymentFactory(
            user=cls.user_worker, shop=cls.shop, function_group=cls.group_worker, network=cls.network
        )
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir, network=cls.network
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs, network=cls.network
        )
        cls.approve_event_type, _created = EventType.objects.get_or_create(code=APPROVE_EVENT_TYPE, network=cls.network)
        cls.dt = datetime.now().date()
        cls.plan_not_approved = WorkerDayFactory(
            is_approved=False,
            is_fact=False,
            shop=cls.shop,
            employment=cls.employment_worker,
            worker=cls.user_worker,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
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
            FunctionGroup.objects.create(group=self.group_dir, func='WorkerDay_approve', method='POST')
            GroupWorkerDayPermission.objects.create(
                group=self.group_dir,
                worker_day_permission=WorkerDayPermission.objects.get(
                    action=WorkerDayPermission.APPROVE,
                    graph_type=WorkerDayPermission.PLAN,
                    wd_type=WorkerDay.TYPE_WORKDAY,
                ),
            )
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
