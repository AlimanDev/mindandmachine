import datetime
import json
from datetime import date
from unittest import skip

from django.conf import settings
from django.utils import timezone

from src.base.models import (
    Employment,
    User,
)
from src.timetable.models import (
    WorkerDay,
    WorkerDayChangeRequest
)
from src.util.models_converter import Converter
from src.util.test import LocalTestCase

def create_stuff(shop_id: int) -> User:
    user = User.objects.create_user(
        'staff1',
        'staff1@test.ru',
        '4242',
        last_name='Иванов',
        first_name='Иван',
    )
    employment = Employment.objects.create(
        user=user,
        shop_id=shop_id,
        dt_hired=timezone.now() - datetime.timedelta(days=5),
        dt_fired=timezone.now() + datetime.timedelta(days=3),
    )

    return user, employment


class TestCashier(LocalTestCase):
    def test_change_password(self):
        self.auth()

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': self.user1.id,
            'shop_id': self.root_shop.id,
            'old_password': 'qqq',
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        # {'error_type': 'AccessForbidden', 'error_message': ''}
        self.assertEqual(response.json()['code'], 403)
        self.assertEqual(response.json()['data']['error_type'], 'AccessForbidden')

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 5,
            'shop_id': self.shop.id,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        # {'error_type': 'DoesNotExist', 'error_message': 'error in api_method'}
        self.assertEqual(response.json()['code'], 403)
        # self.assertEqual(response.json()['data']['error_type'], 'AccessForbidden')
        # self.assertEqual(response.json()['data']['error_message'], 'You are not allowed to edit this user')

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'shop_id': self.shop.id,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'shop_id': self.shop.id,
            'old_password': 'new_password',
            'new_password': self.USER_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        self.user1.save()
        self.auth()

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'shop_id': self.shop.id,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

    def test_change_cashier_info(self):
        self.auth()
        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 1,
            'shop_id': self.shop.id,
            'first_name': 'Benedick',
            'password': self.USER_PASSWORD
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        self.assertEqual(response.json()['code'], 404)
        # self.assertEqual(response.json()['data']['new_first_name'], 'Benedick')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 4,
            'shop_id': self.shop.id,
            'first_name': 'Boss',
            'password': self.USER_PASSWORD
        })
        self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json()['code'], 403)
        # self.assertEqual(response.json()['data']['error_message'], 'You are not allowed to edit this user')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 2,
            'shop_id': self.shop.id,
            'first_name': 'Viktor',
            'password': self.USER_PASSWORD
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json()['code'], 200)
        # self.assertEqual(response.json()['data']['new_first_name'], 'Viktor')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 1,
            'shop_id': self.root_shop.id,
            'first_name': 'Viktor',
            'password': self.USER_PASSWORD
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json()['code'], 403)
        # self.assertEqual(response.json()['data']['error_message'], 'You are not allowed to edit this group')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 1,
            'shop_id': self.root_shop.id,
            'first_name': 'Viktor',
            'middle_name': 'middle_name',
            'last_name': 'last_name',
            'birthday': date(1990, 2, 3),
        })
        self.assertEqual(response.json()['code'], 400)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json()['code'], 200)
        # self.assertEqual(response.json()['data']['new_first_name'], 'Viktor')
        # self.assertEqual(response.json()['data']['new_middle_name'], 'middle_name')
        # self.assertEqual(response.json()['data']['new_last_name'], 'last_name')
        # self.assertEqual(response.json()['data']['new_birthday'], '1990-02-03')


class TestGetCashierList(LocalTestCase):
    """Tests for timetable/cashier/get_cashiers_list"""
    url = '/api/timetable/cashier/get_cashiers_list'

    def setUp(self):
        super().setUp(worker_day=False)
        self.staff1, self.employment = create_stuff(self.root_shop.id)

    def test_dt_from(self):
        # staff1 included - fired after dt_from filter
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': 1,
                'dt_from': (timezone.now() - datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() - datetime.timedelta(days=5)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

        # staff1 excluded - fired before dt_from filter
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': 1,
                'dt_from': (timezone.now() - datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() - datetime.timedelta(days=6)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

    def test_dt_to(self):
        # staff1 included - hired before dt_to value
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': 1,
                'dt_from': (timezone.now() + datetime.timedelta(days=1)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() + datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

        # staff1 excluded - hired after dt_to value
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': 1,
                'dt_from': (timezone.now() + datetime.timedelta(days=3)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() + datetime.timedelta(days=5)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)


class TestGetNotWorkingCashierList(LocalTestCase):
    url = '/api/timetable/cashier/get_not_working_cashiers_list'

    def setUp(self, worker_day=False):
        super().setUp(worker_day)
        self.staff1, self.employment = create_stuff(self.shop.id)
        self.wd: WorkerDay = WorkerDay.objects.create(
            type=WorkerDay.TYPE_VACATION,
            worker=self.staff1,
            employment=self.employment,
            dt=timezone.now().date(),
        )

    def test_dt_from(self):
        # staff1 included - fired after dt_from value
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': self.shop.id,
                'dt_from': (timezone.now() + datetime.timedelta(days=2)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() + datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

        # staff1 excluded - fired before dt_from value
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': self.shop.id,
                'dt_from': (timezone.now() + datetime.timedelta(days=3)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() + datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 0)

    def test_dt_to(self):
        # staff1 included - hired before dt_to filter
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': self.shop.id,
                'dt_from': (timezone.now() - datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() - datetime.timedelta(days=5)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

        # staff1 excluded - hired after dt_to filter
        with self.auth_user():
            response = self.api_get(self.url, {
                'shop_id': self.shop.id,
                'dt_from': (timezone.now() - datetime.timedelta(days=10)).date().strftime(
                    settings.QOS_DATE_FORMAT),
                'dt_to': (timezone.now() - datetime.timedelta(days=6)).date().strftime(
                    settings.QOS_DATE_FORMAT),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 0)


class TestSelectCashiers(LocalTestCase):
    url = '/api/timetable/cashier/select_cashiers'

    # TODO Add more test cases

    def setUp(self):
        super().setUp(worker_day=True)

    def test_success(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_ids": json.dumps([self.user2.pk]),
                "shop_id": self.shop.pk,
                "work_types": json.dumps([self.work_type3.pk]),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)
        self.assertEqual(response.json()['data'][0]['id'], self.user2.pk)


class TestGetCashierTimetable(LocalTestCase):
    url = '/api/timetable/cashier/get_cashier_timetable'

    def setUp(self, worker_day=True):
        super().setUp(worker_day=worker_day)

    # TODO Add more test cases

    def test_success(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_ids": json.dumps([self.user2.pk]),
                "shop_id": self.shop.pk,
                "from_dt": Converter.convert_date(timezone.now()),
                "to_dt": Converter.convert_date(timezone.now()),
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)
        self.assertIsNotNone(response.json()['data'].get(str(self.user2.pk)))


class TestGetCashierInfo(LocalTestCase):
    url = '/api/timetable/cashier/get_cashier_info'

    def test_general_info(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "info": "general_info"
            })
        self.assertResponseCodeEqual(response, 200)
        general_info = {'id': 2, 'username': 'user2', 'first_name': 'Иван2',
                        'last_name': 'Иванов', 'middle_name': None,
                        'avatar_url': None, 'sex': 'F', 'phone_number': None, 'email': 'u2@b.b',
                        'shop_id': self.shop.id, 'dt_hired': '2019-01-01', 'dt_fired': None, 'auto_timetable': True,
                        'salary': 0.0, 'is_fixed_hours': False, 'is_ready_for_overworkings': False,
                        'tabel_code': None,
                        'position': '',
                        'position_id': ''}

        self.assertEqual(response.json()['data'].get('general_info'), general_info)

    def test_work_type_info(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "info": "work_type_info"
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertIsNotNone(response.json()['data'].get('work_type_info'))

    def test_constraints_info(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "info": "constraints_info"
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertIsNotNone(response.json()['data'].get('constraints_info'))

    def test_work_hours(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "info": "work_hours"
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertIsNotNone(response.json()['data'].get('work_hours'))


class TestGetWorkerDay(LocalTestCase):
    url = '/api/timetable/cashier/get_worker_day'

    def setUp(self):
        super().setUp(worker_day=True)

    def test_success(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_id": self.user2.id,
                "shop_id": self.shop.id,
                "dt": Converter.convert_date(timezone.now()),
            })
        self.assertResponseCodeEqual(response, 200)

    def test_not_found(self):
        with self.auth_user():
            response = self.api_get(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "dt": Converter.convert_date(timezone.now() - datetime.timedelta(days=16)),
            })
        self.assertResponseCodeEqual(response, 404)
        self.assertErrorType(response, 'DoesNotExist')


class TestSetWorkerDay(LocalTestCase):
    url = '/api/timetable/cashier/set_worker_day'

    def setUp(self):
        super().setUp(worker_day=True)

    def test_success(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "dt": Converter.convert_date(timezone.now()),
                "tm_work_start": "11:00:00",
                "tm_work_end": "12:00:00",
                "type": WorkerDay.TYPE_BUSINESS_TRIP,
                "comment": "I'm a test"
            })
        self.assertResponseCodeEqual(response, 200)
        data = response.json()['data']
        self.assertEqual(data['action'], 'update', data)

        wd: WorkerDay = WorkerDay.objects.filter(
            worker_id=self.user2.pk,
            dt=timezone.now().date()).order_by('id').last()
        self.assertEqual(wd.dttm_work_start, datetime.datetime.combine(timezone.now().date(), datetime.time(11, 00)))
        self.assertEqual(wd.dttm_work_end, datetime.datetime.combine(timezone.now().date(), datetime.time(12, 00)))
        self.assertEqual(wd.type, WorkerDay.TYPE_BUSINESS_TRIP)
        self.assertIsNotNone(wd.parent_worker_day)
        
    def test_update_range(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": self.user2.pk,
                "shop_id": self.shop.id,
                "dt": Converter.convert_date(timezone.now()),
                "dt_to": Converter.convert_date(timezone.now() + datetime.timedelta(days=2)),
                "tm_work_start": "11:00:00",
                "tm_work_end": "12:00:00",
                "type": WorkerDay.TYPE_BUSINESS_TRIP,
                "comment": "I'm a test"
            })
        self.assertResponseCodeEqual(response, 200)
        data = response.json()['data']
        self.assertEqual(data[0]['action'], 'update', data)

        wd: WorkerDay = WorkerDay.objects.filter(worker_id=self.user2.pk, dt=timezone.now().date()).last()
        wd2: WorkerDay = WorkerDay.objects.filter(worker_id=self.user2.pk, dt=timezone.now().date() + datetime.timedelta(days=1)).last()
        self.assertEqual(wd.dttm_work_start, datetime.datetime.combine(timezone.now().date(), datetime.time(11, 00)))
        self.assertEqual(wd.dttm_work_end, datetime.datetime.combine(timezone.now().date(), datetime.time(12, 00)))
        self.assertEqual(wd.type, WorkerDay.TYPE_BUSINESS_TRIP)
        self.assertIsNotNone(wd.parent_worker_day)
        self.assertEqual(wd2.dttm_work_start, datetime.datetime.combine(timezone.now().date() + datetime.timedelta(days=1), datetime.time(11, 00)))
        self.assertEqual(wd2.dttm_work_end, datetime.datetime.combine(timezone.now().date() + datetime.timedelta(days=1), datetime.time(12, 00)))
        self.assertEqual(wd2.type, WorkerDay.TYPE_BUSINESS_TRIP)
        self.assertIsNotNone(wd2.parent_worker_day)

    def test_create_range(self):
        user = User.objects.create_user(
            'user8',
            'k@k.k',
            '4242',
            id=8,
            last_name='Дурак7',
            first_name='Иван7',
        )
        employment = Employment.objects.create(
            user=user,
            shop=self.shop,
            function_group=self.employee_group,
        )
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": user.pk,
                'shop_id': self.shop.id,
                "dt": Converter.convert_date(timezone.now()),
                "dt_to": Converter.convert_date(timezone.now() + datetime.timedelta(days=2)),
                "tm_work_start": "11:00:00",
                "tm_work_end": "12:00:00",
                "type": WorkerDay.TYPE_WORKDAY,
                "comment": "I'm a test"
            })
        self.assertResponseCodeEqual(response, 200)
        data = response.json()['data']
        self.assertEqual(data[0]['action'], 'create', data)
        wd: WorkerDay = WorkerDay.objects.filter(worker_id=8, dt=timezone.now().date()).last()
        wd2: WorkerDay = WorkerDay.objects.filter(worker_id=8, dt=timezone.now().date() + datetime.timedelta(days=1)).last()
        self.assertEqual(wd.dttm_work_start, datetime.datetime.combine(timezone.now().date(), datetime.time(11, 00)))
        self.assertEqual(wd.dttm_work_end, datetime.datetime.combine(timezone.now().date(), datetime.time(12, 00)))
        self.assertEqual(wd.type, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd2.dttm_work_start, datetime.datetime.combine(timezone.now().date() + datetime.timedelta(days=1), datetime.time(11, 00)))
        self.assertEqual(wd2.dttm_work_end, datetime.datetime.combine(timezone.now().date() + datetime.timedelta(days=1), datetime.time(12, 00)))
        self.assertEqual(wd2.type, WorkerDay.TYPE_WORKDAY)
#
# class TestGetWorkerDayLogs(LocalTestCase):
#     url = '/api/timetable/cashier/get_worker_day_logs'


class TestDeleteWorkerDay(LocalTestCase):
    url = '/api/timetable/cashier/delete_worker_day'

    def setUp(self, worker_day=False):
        super().setUp(worker_day)
        self.now = timezone.now()

        self.staff, self.employment = create_stuff(self.shop.id)
        self.wd_root = WorkerDay.objects.create(
            worker_id=self.staff.pk,
            shop=self.employment.shop,
            employment=self.employment,
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.now.date())
        self.wd_child = WorkerDay.objects.create(
            worker_id=self.staff.pk,
            shop=self.employment.shop,
            employment=self.employment,
            type=WorkerDay.TYPE_VACATION,
            dt=self.now.date(),
            parent_worker_day_id=self.wd_root.pk
        )
        self.wd_child2 = WorkerDay.objects.create(
            worker_id=self.staff.pk,
            shop=self.employment.shop,
            employment=self.employment,
            type=WorkerDay.TYPE_VACATION,
            dt=self.now.date(),
            parent_worker_day_id=self.wd_child.pk)

    def test_success(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_day_id": self.wd_child.pk
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertIsNone(WorkerDay.objects.filter(pk=self.wd_child.pk).first())
        self.wd_child2 = self.refresh_model(self.wd_child2)
        self.assertEqual(self.wd_child2.parent_worker_day_id, self.wd_root.pk)

    def test_not_exists(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_day_id": -1
            })
        self.assertResponseCodeEqual(response, 404)
        self.assertErrorType(response, "DoesNotExist")

    def test_no_parent(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_day_id": self.wd_root.pk
            })
        self.assertResponseCodeEqual(response, 500)
        self.assertErrorType(response, "InternalError")


class TestSetWorkerRestrictions(LocalTestCase):
    url = '/api/timetable/cashier/set_worker_restrictions'

    def setUp(self):
        super().setUp()
        
    
    def test_set_week_availability(self):
        with self.auth_user():

            response = self.api_post(self.url, {
                "worker_id": 1,
                "shop_id": self.root_shop.id,
                "week_availability": 4,
                "dt_new_week_availability_from": Converter.convert_date(date(2019, 2, 10)),
                "shift_hours_length": '-',
                'norm_work_hours': 100
            })
            self.assertEqual(response.json()['code'], 200)
            correct_data = {
                'week_availability': 4,
                'dt_new_week_availability_from': date(2019, 2, 10)
            }
            self.assertEqual(
                Employment.objects.filter(
                    user_id=self.user1.id,
                    shop_id=self.root_shop.id
                ).values(
                    'week_availability',
                    'dt_new_week_availability_from'
                )[0],
                correct_data
            )

    def test_set_data(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": 1,
                "shop_id": self.root_shop.id,
                "worker_sex": "F",
                "work_type_info": json.dumps([{"work_type_id":self.work_type1.id,"priority":0}]),
                "is_ready_for_overworkings" : True,
                "is_fixed_hours" : True,
                "norm_work_hours": 50,
                "shift_hours_length": "6-8",
                "week_availability" : 7
            })
            correct_data = {
                'is_ready_for_overworkings': True,
                'is_fixed_hours': True,
                'norm_work_hours': 50,
                'shift_hours_length_min': 6,
                'shift_hours_length_max': 8,
                'week_availability': 7,
            }
            self.assertEqual(response.json()['code'], 200)
            self.assertEqual(
                User.objects.get(pk=1).sex,
                'F'
            )
            self.assertEqual(
                Employment.objects.filter(user_id=1,shop_id=self.root_shop.id).values(
                    'is_ready_for_overworkings',
                    'is_fixed_hours',
                    'norm_work_hours',
                    'shift_hours_length_min',
                    'shift_hours_length_max',
                    'week_availability'
                )[0],
                correct_data
            )

    def test_set_week_availability_without_date(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": 1,
                "shop_id": self.root_shop.id,
                "week_availability": 4,
                "shift_hours_length": '-'
            })
            correct_data = {
                'code': 400, 
                'data': {
                    'error_type': 'ValueException', 
                    'error_message': "[('week_availability', ['week_availability != 7 dt_new_week_availability_from should be defined'])]"
                }, 
                    'info': None
            }
            self.assertEqual(response.json(), correct_data)


class TestCreateCashier(LocalTestCase):
    url = '/api/timetable/cashier/create_cashier'

    def test_success(self):
        now = timezone.now()
        with self.auth_user():
            response = self.api_post(self.url, {
                "first_name": "James",
                "last_name": "Bond",
                "middle_name": "007",
                "username": "jb007",
                "password": "mi7",
                "dt_hired": Converter.convert_date(now),
                "shop_id": self.shop.pk,
            })
        self.assertResponseCodeEqual(response, 200)
        uid = response.json()['data'].get("id")
        self.assertIsNotNone(uid)

        user = User.objects.get(pk=uid)
        employment = Employment.objects.get(
            user=user,
            shop=self.shop
        )
        self.assertEqual(user.first_name, "James")
        self.assertEqual(user.last_name, "Bond")
        self.assertEqual(user.middle_name, "007")
        self.assertEqual(user.username, f"u{uid}")
        self.assertTrue(user.check_password("mi7"))

        self.assertEqual(employment.dt_hired, now.date())
        self.assertIsNone(employment.dt_fired)
        self.assertEqual(employment.shop_id, self.shop.pk)

#
# class TestDublicateCashierTable(LocalTestCase):
#     url = '/api/timetable/cashier/dublicate_cashier_table'


# class TestDeleteCashier(LocalTestCase):
#     url = '/api/timetable/cashier/delete_cashier'
#
#     def setUp(self, worker_day=False):
#         super().setUp(worker_day)
#         self.now = timezone.now()
#         self.user = self.user2
#         self.user.dt_fired = None
#         self.user.save()
#
#     def test_success(self):
#         self.assertIsNone(self.user.dt_fired)
#         with self.auth_user():
#             response = self.api_post(self.url, {
#                 "user_id": self.user.pk,
#                 "dt_fired": Converter.convert_date(self.now)
#             })
#         self.assertResponseCodeEqual(response, 200)
#         self.user = self.refresh_model(self.user)
#         self.assertEqual(self.user.dt_fired, self.now.date())
#
#     def test_not_found(self):
#         with self.auth_user():
#             response = self.api_post(self.url, {
#                 "user_id": -1,
#                 "dt_fired": Converter.convert_date(self.now)
#             })
#         self.assertResponseCodeEqual(response, 400)
#         self.assertErrorType(response, "DoesNotExist")


@skip("change request is not used")
class TestGetChangeRequest(LocalTestCase):
    url = '/api/timetable/cashier/get_change_request'

    def setUp(self, worker_day=False):
        super().setUp(worker_day)
        self.user, self.employment = create_stuff(self.shop.pk)
        self.now = timezone.now().replace(microsecond=0)
        self.wd_today = WorkerDayChangeRequest.objects.create(
            worker_id=self.user.pk, dt=self.now.date(),
            type=WorkerDay.TYPE_VACATION
        )
        self.wd_tomorrow = WorkerDayChangeRequest.objects.create(
            worker_id=self.user.pk, dt=(self.now + datetime.timedelta(days=1)).date(),
            type=WorkerDay.TYPE_WORKDAY
        )

    def test_success(self):
        # Today request
        with self.auth_user():
            response = self.api_get(self.url, {
                'worker_id': self.user.id,
                "shop_id": self.root_shop.id,
                'dt': Converter.convert_date(self.now)
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertEqual(response.json()['data']['type'],
                        WorkerDay.TYPE_VACATION)

        # Tomorrow request
        with self.auth_user():
            response = self.api_get(self.url, {
                'worker_id': self.user.id,
                'dt': Converter.convert_date(self.now + datetime.timedelta(days=1))
            })
        self.assertResponseCodeEqual(response, 200)
        self.assertEqual(response.json()['data']['type'],
                        WorkerDay.TYPE_WORKDAY)

        # Yesterday request - no request
        with self.auth_user():
            response = self.api_get(self.url, {
                'worker_id': self.user.id,
                'dt': Converter.convert_date(self.now - datetime.timedelta(days=1))
            })
        self.assertResponseCodeEqual(response, 200)


@skip("change request is not used")
class TestRequestWorkerDay(LocalTestCase):
    url = '/api/timetable/cashier/request_worker_day'

    def setUp(self, worker_day=False):
        super().setUp(worker_day)
        self.user, self.employment = create_stuff(self.shop.pk)

    def test_required(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": self.staff.id,
                "shop_id": self.shop.id,
                "dt": Converter.convert_date(timezone.now().date()),
                "type": 'V'
            })
        self.assertResponseCodeEqual(response, 200)
        req = WorkerDayChangeRequest.objects.filter(
            worker_id=self.staff.id, type=WorkerDay.TYPE_VACATION
        ).first()
        self.assertIsNotNone(req)
        self.assertIsNone(req.dttm_work_start)
        self.assertIsNone(req.dttm_work_end)

    def test_all_fields(self):
        now = timezone.now().replace(microsecond=0)

        with self.auth_user():
            response = self.api_post(self.url, {
                "worker_id": self.staff.id,
                "shop_id": self.shop.id,
                "dt": Converter.convert_date(now.date()),
                "type": 'V',
                'tm_work_start': Converter.convert_time(now),
                'tm_work_end': Converter.convert_time(now + datetime.timedelta(hours=2)),
                'wish_text': "lorem ipsum"
            })
        self.assertResponseCodeEqual(response, 200)

        req = WorkerDayChangeRequest.objects.filter(
            worker_id=self.staff.id, type=WorkerDay.TYPE_VACATION
        ).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.dttm_work_start, now)
        self.assertEqual(req.dttm_work_end, now + datetime.timedelta(hours=2))
        self.assertEqual(req.wish_text, "lorem ipsum")


@skip("change request is not used")
class TestHandleWorkerDayRequest(LocalTestCase):
    url = '/api/timetable/cashier/handle_change_request'

    def setUp(self, worker_day=False):
        super().setUp(worker_day)
        self.worker, self.employment = create_stuff(self.root_shop.id)
        self.req: WorkerDayChangeRequest = WorkerDayChangeRequest.objects.create(
            worker=self.worker, dt=timezone.now().today(), type=WorkerDay.TYPE_VACATION,
        )

    def test_approve(self):
        self.assertEqual(WorkerDay.objects.filter(worker_id=self.worker.id).count(), 0)
        with self.auth_user():
            response = self.api_post(self.url, {
                "request_id": self.req.id,
                "action": "A"
            })
        self.req = self.refresh_model(self.req)
        self.assertResponseCodeEqual(response, 200)
        self.assertEqual(self.req.status_type, WorkerDayChangeRequest.TYPE_APPROVED)
        self.assertEqual(WorkerDay.objects.filter(worker_id=self.worker.id).count(), 1)

    def test_decline(self):
        self.assertEqual(WorkerDay.objects.filter(worker_id=self.worker.id).count(), 0)
        with self.auth_user():
            response = self.api_post(self.url, {
                "request_id": self.req.id,
                "action": "D"
            })
        self.req = self.refresh_model(self.req)
        self.assertResponseCodeEqual(response, 200)
        self.assertEqual(self.req.status_type, WorkerDayChangeRequest.TYPE_DECLINED)
        self.assertEqual(WorkerDay.objects.filter(worker_id=self.worker.id).count(), 0)

    def test_bad_action(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "request_id": self.req.id,
                "action": "EEE"
            })
        self.assertResponseCodeEqual(response, 500)

    def test_bad_request_id(self):
        with self.auth_user():
            response = self.api_post(self.url, {
                "request_id": 99999,
                "action": "A"
            })
        self.assertResponseCodeEqual(response, 400)
