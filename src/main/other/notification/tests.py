from src.util.test import LocalTestCase
from src.db.models import Notifications, User, Event, WorkerDayCashboxDetails, WorkerDay
import json
from django.utils import timezone
from datetime import timedelta

class TestNotifications(LocalTestCase):
    def setUp(self):
        super().setUp()

        for number in range(1, 6):
            event = Event.objects.create(
                text='Test event #{}'.format(number)
            )
            Notifications.objects.create(
                id=number,
                to_worker=self.user1,
                event=event
            )

        for number in range(6, 11):
            event = Event.objects.create(
                text='Test event #{}'.format(number)
            )
            Notifications.objects.create(
                id=number,
                to_worker=self.user1,
                event=event,
                was_read=True
            )

        dt = timezone.now().date() + timedelta(days=1)

        self.wdcd = WorkerDayCashboxDetails.objects.create(
            dttm_from='{} 09:00:00'.format(dt),
            dttm_to='{} 21:00:00'.format(dt),
            work_type=self.work_type1,
            status=WorkerDayCashboxDetails.TYPE_VACANCY,
            is_vacancy=True,
        )

        self.user_worker_day = WorkerDay.objects.qos_current_version().filter(
            worker=self.user1,
            dt=dt
        ).first()
        self.user_worker_day.type = WorkerDay.Type.TYPE_HOLIDAY.value
        self.user_worker_day.save()

        event = Event.objects.create(
            text='Уведомление с каким-то предложением / подтверждением.',
            department=self.shop,
            workerday_details=self.wdcd
        )

        Notifications.objects.create(
            id=11,
            event=event,
            to_worker=self.user1,
        )

    def test_get_notifications(self):
        self.auth()

        response = self.api_get('/api/other/notifications/get_notifications2?count=5')
        self.assertEqual(len(response.json['data']['notifications']), 5)
        self.assertEqual(response.json['data']['notifications'][-1]['id'], 7)
        self.assertEqual(response.json['data']['unread_count'], 6)

        response = self.api_get('/api/other/notifications/get_notifications2?count=5&pointer=1')
        self.assertEqual(len(response.json['data']['notifications']), 5)
        self.assertEqual(response.json['data']['notifications'][-1]['id'], 2)
        self.assertEqual(response.json['data']['unread_count'], 6)

        response = self.api_get('/api/other/notifications/get_notifications2')
        self.assertEqual(len(response.json['data']['notifications']), 11)
        self.assertEqual(response.json['data']['notifications'][-1]['id'], 1)
        self.assertEqual(response.json['data']['unread_count'], 6)

        self.wdcd.dttm_deleted = timezone.now()
        self.wdcd.save()

        response = self.api_get('/api/other/notifications/get_notifications2')
        self.assertEqual(len(response.json['data']['notifications']), 10)
        self.assertEqual(response.json['data']['notifications'][-1]['id'], 1)
        self.assertEqual(response.json['data']['unread_count'], 6)

        self.wdcd.worker_day = self.user_worker_day
        self.wdcd.save()

        response = self.api_get('/api/other/notifications/get_notifications2')
        self.assertEqual(len(response.json['data']['notifications']), 11)
        self.assertEqual(response.json['data']['notifications'][-1]['id'], 1)
        self.assertEqual(response.json['data']['unread_count'], 6)

        self.user_worker_day.worker = self.user2
        self.user_worker_day.save()

        response = self.api_get('/api/other/notifications/get_notifications2')
        self.assertEqual(len(response.json['data']['notifications']), 10)
        self.assertEqual(response.json['data']['notifications'][-1]['id'], 1)
        self.assertEqual(response.json['data']['unread_count'], 6)

    def test_set_notifications_read(self):
        self.auth()

        response = self.api_post('/api/other/notifications/set_notifications_read', {'ids': json.dumps([1, 2, 3])})
        notifications = Notifications.objects.filter(id__in=[1, 2, 3])
        self.assertEqual(notifications[0].was_read, True)
        self.assertEqual(notifications[1].was_read, True)
        self.assertEqual(notifications[2].was_read, True)

    def test_do_notify_action(self):
        self.auth()

        self.assertEqual(WorkerDayCashboxDetails.objects.get(pk=self.wdcd.id).worker_day, None)
        response = self.api_post('/api/other/notifications/do_notify_action', {'notify_id': 11})
        self.assertEqual(WorkerDayCashboxDetails.objects.get(pk=self.wdcd.id).worker_day.worker.id, 1)
