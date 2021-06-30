from rest_framework.test import APITestCase
from unittest import mock
from datetime import date, timedelta
from django.test import override_settings
from django.core import mail
from django.conf import settings
from src.recognition.utils import check_duplicate_biometrics
from src.recognition.events import DUPLICATE_BIOMETRICS
from src.recognition.models import UserConnecter
from src.util.mixins.tests import TestsHelperMixin
from src.recognition.api.recognition import Recognition
from src.events.models import EventType
from src.notifications.models import EventEmailNotification

class TestTickPhotos(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        UserConnecter.objects.create(user=cls.user1, partner_id=1)
        cls.user1.avatar = 'photo/1'
        cls.user1.save()
        cls.user3.avatar = 'photo/3'
        cls.user3.save()
        cls.user2.email = 'test@test.com'
        cls.user2.save()
        UserConnecter.objects.create(user=cls.user2, partner_id=2)
        cls.dt = date.today()
        cls.employee1.tabel_code = 'A00001'
        cls.employee1.save()
        cls.employee3.tabel_code = 'A00001'
        cls.employee3.save()
        cls.duplicate_biometrics_event, _created = EventType.objects.get_or_create(
            code=DUPLICATE_BIOMETRICS, network=cls.network)

    def setUp(self):
        self._set_authorization_token(self.user2.username)

    def test_check_duplicate(self):
        subject = 'Дублирование биометрии'
        event_email_notification = EventEmailNotification.objects.create(
            event_type=self.duplicate_biometrics_event,
            subject=subject,
            system_email_template='notifications/email/duplicate_biometrics.html',
        )
        event_email_notification.users.add(self.user2)
        with mock.patch.object(Recognition, 'identify', lambda x, y: 1) as identify:
            with override_settings(CELERY_TASK_ALWAYS_EAGER=True):
                check_duplicate_biometrics(None, self.user3, shop_id=self.shop2.id)
        self.assertEqual(len(mail.outbox), 1)
        body = f'Здравствуйте, {self.user2.first_name}!\n\nОдинаковые биометрические параметры сотрудников.\n' +\
        f'Первый сотрудник: {self.user3.last_name} {self.user3.first_name}\nТабельный номер: {self.employee3.tabel_code}\nОтдел: {self.shop.name}\nСсылка на биошаблон: {settings.EXTERNAL_HOST}/_i/media/photo/3\n' +\
        f'Второй сотрудник: {self.user1.last_name} {self.user1.first_name}\nТабельный номер: {self.employee1.tabel_code}\nОтдел: {self.root_shop.name}\nСсылка на биошаблон: {settings.EXTERNAL_HOST}/_i/media/photo/1' +\
        '\n\nПисьмо отправлено роботом.'
        self.assertEqual(mail.outbox[0].body, body)
