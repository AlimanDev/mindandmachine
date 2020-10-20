import json
from datetime import datetime, time

from rest_framework.test import APITestCase
from django.utils.timezone import now
from django.conf import settings

from src.base.models import FunctionGroup
from src.timetable.models import ShopMonthStat, WorkerDay, WorkerDayCashboxDetails,WorkType, WorkTypeName
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


settings.CELERY_TASK_ALWAYS_EAGER = True


class TestAutoSettings(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/auto_settings/set_timetable/'
        self.dt = now().date()

        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин')
        self.work_type_name2 = WorkTypeName.objects.create(name='Ломбард')
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)
        self.work_type2 = WorkType.objects.create(
            work_type_name=self.work_type_name2,
            shop=self.shop)

        self.client.force_authenticate(user=self.user1)


    def test_set_timetable_new(self):

        timetable = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            status=ShopMonthStat.PROCESSING,
            dttm_status_change=now()
        )

        dt = now().date()
        tm_from = time(10, 0, 0)
        tm_to = time(20, 0, 0)

        dttm_from = Converter.convert_datetime(
            datetime.combine(dt, tm_from),
        )

        dttm_to = Converter.convert_datetime(
            datetime.combine(dt, tm_to),
        )
        self.assertEqual(len(WorkerDay.objects.all()), 0)
        self.assertEqual(len(WorkerDayCashboxDetails.objects.all()), 0)

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.user3.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'dttm_from': dttm_from,
                                 'dttm_to': dttm_to,
                                 'type': self.work_type2.id
                             }]
                             }
                        ]
                    },
                    self.user4.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'H',
                             }
                        ]
                    }
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        wd = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type=WorkerDay.TYPE_WORKDAY
        )
        self.assertEqual(len(wd), 1)

        self.assertEqual(WorkerDayCashboxDetails.objects.filter(
            worker_day=wd[0],
            dttm_from=datetime.combine(dt, tm_from),
            dttm_to=datetime.combine(dt, tm_to),
            work_type=self.work_type2,
        ).count(), 1)

        self.assertEqual(WorkerDay.objects.filter(
            worker=self.user4,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            shop__isnull=True,
            dttm_work_start__isnull=True,
            dttm_work_end__isnull=True
        ).count(), 1)



    def test_set_timetable_change_existed(self):
        timetable = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            status=ShopMonthStat.PROCESSING,
            dttm_status_change=now()
        )

        dt = now().date()
        tm_from = time(10, 0, 0)
        tm_to = time(20, 0, 0)

        dttm_from = Converter.convert_datetime(
            datetime.combine(dt, tm_from),
        )

        dttm_to = Converter.convert_datetime(
            datetime.combine(dt, tm_to),
        )


        self.wd1_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
        )
        self.wd1_plan_not_approved = WorkerDay.objects.create(
            worker=self.user2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_HOLIDAY,
            parent_worker_day=self.wd1_plan_approved
        )

        self.wd2_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user3,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
        )

        self.wd3_plan_not_approved = WorkerDay.objects.create(
            worker=self.user4,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_HOLIDAY,
        )

        response = self.client.post(self.url, {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.user2.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'dttm_from': dttm_from,
                                 'dttm_to': dttm_to,
                                 'type': self.work_type2.id
                             }]
                             }
                        ]
                    },
                    self.user3.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'dttm_from': dttm_from,
                                 'dttm_to': dttm_to,
                                 'type': self.work_type2.id
                             }]
                             }
                        ]
                    },
                    self.user4.id: {
                        'workdays': [
                            {'dt': Converter.convert_date(dt),
                             'type': 'H',
                             }
                        ]
                    }
                }
            })
        })

        self.assertEqual(response.status_code, 200)

        self.assertTrue(WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, tm_from),
            dttm_work_end = datetime.combine(self.dt, tm_to),
            is_approved=True,
            id=self.wd1_plan_approved.id
        ).exists())

        wd1 = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type=WorkerDay.TYPE_WORKDAY,
            id=self.wd1_plan_not_approved.id,
            is_approved = False
        )
        self.assertEqual(len(wd1), 1)

        wd2 = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user3,
            dt=dt,
            dttm_work_start=datetime.combine(dt, tm_from),
            dttm_work_end=datetime.combine(dt, tm_to),
            type=WorkerDay.TYPE_WORKDAY,
            parent_worker_day_id=self.wd2_plan_approved.id,
            is_approved=False
        )
        self.assertEqual(len(wd2), 1)

        self.assertEqual(WorkerDay.objects.filter(
            worker=self.user4,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            dttm_work_start__isnull=True,
            dttm_work_end__isnull=True,
            shop_id__isnull=True,
            parent_worker_day__isnull=True,
            is_approved=False
        ).count(), 1)

        self.assertEqual(WorkerDayCashboxDetails.objects.filter(
            worker_day__in=[wd1[0], wd2[0]],
            dttm_from=datetime.combine(dt, tm_from),
            dttm_to=datetime.combine(dt, tm_to),
            work_type=self.work_type2,
        ).count(), 2)
