from unittest import mock
from datetime import date, datetime, time, timedelta

from rest_framework import status
from rest_framework.test import APITestCase
from django.test import override_settings
from django.core import mail
from django.utils.translation import gettext as _
import requests

from src.base.models import User
from src.recognition.utils import check_duplicate_biometrics
from src.recognition.events import DUPLICATE_BIOMETRICS
from src.recognition.models import Tick, TickPhoto, UserConnecter
from src.recognition.api.recognition import Recognition, Tevian
from src.timetable.models import WorkerDay
from src.util.mixins.tests import TestsHelperMixin
from src.util.mock import mock_request
from src.events.models import EventType
from src.notifications.models import EventEmailNotification
from .factories import TickPointFactory


@mock.patch.object(requests.sessions.Session, 'request', mock_request(status_code=status.HTTP_200_OK))
@mock.patch.object(Tevian, 'login', lambda self: setattr(self, 'token', 'some_token'))
class TestTickPhotos(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
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
        cls.tick_point = TickPointFactory()
        cls.tick = Tick.objects.create(
            dttm=datetime.now(),
            user=cls.user1,
            employee=cls.employee1,
            tick_point=cls.tick_point,
            type=Tick.TYPE_COMING
        )

    def setUp(self):
        self._set_authorization_token(self.user2.username)

    def test_check_duplicate(self):
        subject = 'Дублирование биометрии'
        self.maxDiff = None
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
        self.assertEqual(
            mail.outbox[0].body,
            f'Здравствуйте, {self.user2.first_name}!\n\n\n\n\n\n\n\n\n\n\nОдинаковые биометрические параметры сотрудников.\n\n\n\n\n\n\n'
            f'ФИО\n\n\n{self.user3.last_name} {self.user3.first_name}\n\n\n{self.user1.last_name} {self.user1.first_name}\n\n\n\n\n'
            f'Табельный номер\n\n\n{self.employee3.tabel_code}\n\n\n{self.employee1.tabel_code}\n\n\n\n\nПодразделение\n\n\n{self.shop.name}\n\n\n{self.root_shop.name}\n\n\n\n\n'
            f'Ссылка на биошаблон\n\n\nбиошаблон\n\n\nбиошаблон\n\n\n\n\n\n\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        mail.outbox.clear()
        self.user1.avatar = None
        self.user1.save()
        with mock.patch.object(Recognition, 'identify', lambda x, y: 1) as identify:
            with override_settings(CELERY_TASK_ALWAYS_EAGER=True):
                ret_data = check_duplicate_biometrics(None, self.user3, shop_id=self.shop2.id)
        self.assertEqual(ret_data, "An error occurred while checking duplicate biometrics: The 'avatar' attribute has no file associated with it.")
        self.assertEqual(len(mail.outbox), 0)

    def _test_lateness(self, type, photo_type, dttm, assert_lateness, tick_id=None, assert_tick_lateness=True):
        with mock.patch('src.recognition.views.now', lambda: dttm - timedelta(hours=3)):
            with mock.patch.object(Recognition, 'detect_and_match', lambda x, y, z: {'score': 1, 'liveness': 1}):
                if not tick_id:
                    response = self.client.post(self.get_url('Tick-list'), {'employee_id': self.employee2.id, 'type': type, 'shop_code': self.shop2.code })
                    self.assertEqual(response.status_code, 200)
                    self.assertIsNone(response.json()['lateness'])
                    tick_id = response.json()['id']
                
                with open('src/recognition/test_data/1.jpg', 'rb') as image:
                    response = self.client.post(self.get_url('TickPhoto-list'), {'type': photo_type, 'tick_id': tick_id, 'image': image})
                
                self.assertEqual(response.status_code, 200)
                self.assertEqual(assert_lateness, response.json()['lateness'])
                if assert_tick_lateness:
                    tick = Tick.objects.get(id=tick_id)
                    if assert_lateness:
                        self.assertEqual(tick.lateness, timedelta(seconds=assert_lateness))
                    else:
                        self.assertIsNone(tick.lateness)
                return tick_id

    def test_lateness(self):
        WorkerDay.objects.create(
            dt=self.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop2,
            is_approved=True,
            is_vacancy=True,
            dttm_work_start=datetime.combine(self.dt, time(10)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
        )
        comming_time = datetime.combine(self.dt, time(9))
        leaving_time = datetime.combine(self.dt, time(21))
        tick_id = self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_FIRST, comming_time, None)
        self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_SELF, comming_time, -3600, tick_id=tick_id)
        self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_LAST, comming_time, None, tick_id=tick_id, assert_tick_lateness=False)
        tick_id = self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_FIRST, leaving_time, None)
        self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_SELF, leaving_time, -3600, tick_id=tick_id)
        self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_LAST, leaving_time, None, tick_id=tick_id, assert_tick_lateness=False)
        TickPhoto.objects.all().delete()
        Tick.objects.all().delete()
        WorkerDay.objects.filter(is_fact=True).delete()
        comming_time = datetime.combine(self.dt, time(11))
        leaving_time = datetime.combine(self.dt, time(19))
        tick_id = self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_FIRST, comming_time, None)
        self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_SELF, comming_time, 3600, tick_id=tick_id)
        self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_LAST, comming_time, None, tick_id=tick_id, assert_tick_lateness=False)
        tick_id = self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_FIRST, leaving_time, None)
        self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_SELF, leaving_time, 3600, tick_id=tick_id)
        self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_LAST, leaving_time, None, tick_id=tick_id, assert_tick_lateness=False)
        comming_time = datetime.combine(self.dt + timedelta(1), time(11))
        leaving_time = datetime.combine(self.dt + timedelta(1), time(19))
        tick_id = self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_FIRST, comming_time, None)
        self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_SELF, comming_time, None, tick_id=tick_id)
        self._test_lateness(Tick.TYPE_COMING, TickPhoto.TYPE_LAST, comming_time, None, tick_id=tick_id)
        tick_id = self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_FIRST, leaving_time, None)
        self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_SELF, leaving_time, None, tick_id=tick_id)
        self._test_lateness(Tick.TYPE_LEAVING, TickPhoto.TYPE_LAST, leaving_time, None, tick_id=tick_id)

    def test_recognition_service_unavailable(self):
        """
        Creating TickPhoto when recognition service (e.g. Tevian) is unavailable.
        TickPhoto's and Tick's verification_score and liveness must be set to 1.
        """
        # User has a reference photo
        data = {
            'tick_id': self.tick.id,
            'dttm': self.tick.dttm,
            'image': self.temp_photo,
            'type': TickPhoto.TYPE_FIRST,
        }
        with mock.patch.object(Recognition, 'detect_and_match', mock.Mock(side_effect=requests.exceptions.HTTPError)):
            response = self.client.post(self.get_url('TickPhoto-list'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('verified_score'), 1.0)
        self.assertEqual(response.json().get('liveness'), 1.0)
        self.tick.refresh_from_db()
        self.assertEqual(self.tick.verified_score, 0)   # Only SELF photo's biometrics go to Tick
        photo = TickPhoto.objects.get(tick_id=self.tick.id, type=TickPhoto.TYPE_FIRST)
        self.assertEqual(photo.biometrics_check, False)

        # User doesn't have a no reference new photo
        data['image'] = self.temp_photo,
        data['type'] =  TickPhoto.TYPE_SELF
        UserConnecter.objects.all().delete()
        with mock.patch.object(Recognition, 'identify', mock.Mock(side_effect=requests.exceptions.ConnectionError)):
            response = self.client.post(self.get_url('TickPhoto-list'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('verified_score'), 1.0)
        self.assertEqual(response.json().get('liveness'), 1.0)
        self.tick.refresh_from_db()
        self.assertEqual(self.tick.verified_score, 1.0)
        self.assertEqual(self.tick.biometrics_check, False)
        photo = TickPhoto.objects.get(tick_id=self.tick.id, type=TickPhoto.TYPE_SELF)
        self.assertEqual(photo.biometrics_check, False)

    def test_no_face_found(self):
        data = {
            'tick_id': self.tick.id,
            'dttm': self.tick.dttm,
            'image': self.temp_photo,
            'type': TickPhoto.TYPE_SELF,
        }
        with mock.patch.object(
            requests.Session,
            'request',
            mock_request(
                status_code=status.HTTP_400_BAD_REQUEST,
                json_data={'message': 'no faces found on the image'}
            )
        ):
            response = self.client.post(self.get_url('TickPhoto-list'), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json().get('detail'), _('No faces found on the image.'))
        self.tick.refresh_from_db()
        self.assertEqual(self.tick.biometrics_check, False)
        photo = TickPhoto.objects.get(tick_id=self.tick.id, type=TickPhoto.TYPE_SELF)
        self.assertEqual(photo.biometrics_check, False)
