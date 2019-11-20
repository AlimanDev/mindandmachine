from src.util.test import LocalTestCase
from datetime import timedelta, datetime, time

from django.utils.timezone import now

from src.db.models import AttendanceRecords


class TestURV(LocalTestCase):
    def setUp(self):
        super().setUp()
        dt = now().date() - timedelta(days=3)
        tm_start = time(8,1,0)
        tm_end = time(18,1,0)
        self.create_worker_day(
            self.user2,
            dt,
            datetime.combine(dt, tm_start),
            datetime.combine(dt, tm_end),
        )
        self.create_worker_day(
            self.user3,
            dt,
            datetime.combine(dt, tm_start),
            datetime.combine(dt, tm_end),
        )

        self.tick1 = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(dt, tm_start) - timedelta(minutes=16),
            type=AttendanceRecords.TYPE_COMING,
            verified=1,
        )
        self.tick2 = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(dt, tm_start) + timedelta(minutes=2),
            type=AttendanceRecords.TYPE_COMING,
            verified=1,
        )

        self.tick3 = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(dt, tm_end) + timedelta(minutes=5),
            type=AttendanceRecords.TYPE_LEAVING,
            verified=1,
        )

        self.tick4 = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user3,
            dttm=datetime.combine(dt, tm_start) - timedelta(minutes=10),
            type=AttendanceRecords.TYPE_COMING,
            verified=1,
        )

        self.tick5 = AttendanceRecords.objects.create(
            shop=self.shop2,
            user=self.user2,
            dttm=datetime.combine(now().date() - timedelta(days=2), time(18, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            verified=1,
        )

    def test_get_indicators(self):
        self.auth()
        dt = now().date()
        from_dt = dt - timedelta(days=10)
        response = self.api_get('/api/urv/get_indicators?from_dt={}&to_dt={}&shop_id={}'.format(
            from_dt.strftime("%d.%m.%Y"),
            dt.strftime("%d.%m.%Y"),
            self.shop.id
        ))

        self.assertEqual(response.status_code, 200)
        data = {'code': 200,
                'data': {
                    'ticks_coming_count_fact': 2,
                    'ticks_leaving_count_fact': 1,
                    'ticks_count_fact': 3,
                    'hours_count_fact': 9,
                    'ticks_count_plan': 4,
                    'hours_count_plan': 18,
                    'lateness_count': 1},
                'info': None}

        self.assertEqual(response.json(), data)

    def test_get_user_urv(self):
        self.auth()
        response = self.api_get('/api/urv/get_user_urv?worker_ids=[]&from_dt=01.10.2019&to_dt=08.10.2019&amount_per_page=64&show_outstaff=false&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
