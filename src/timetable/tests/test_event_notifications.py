from unittest import mock

from django.core import mail
from django.db import transaction
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import FunctionGroup
from src.base.tests.factories import ShopFactory, UserFactory, GroupFactory, EmploymentFactory
from src.events.models import EventType
from src.notifications.models import EventEmailNotification
from src.timetable.events import REQUEST_APPROVE_EVENT_TYPE
from src.util.mixins.tests import TestsHelperMixin


class TestRequestApproveEventNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root_shop = ShopFactory()
        cls.shop = ShopFactory(parent=cls.root_shop)
        cls.user_dir = UserFactory(email='dir@example.com')
        cls.user_urs = UserFactory(email='urs@example.com')
        cls.group_dir = GroupFactory(name='Директор')
        FunctionGroup.objects.create(group=cls.group_dir, func='WorkerDay_request_approve', method='POST')
        cls.group_urs = GroupFactory(name='УРС')
        cls.employment_dir = EmploymentFactory(
            user=cls.user_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            user=cls.user_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.request_approve_event = EventType.objects.get(code=REQUEST_APPROVE_EVENT_TYPE)

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_request_approve_email_notification_sent(self):
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
