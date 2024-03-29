import uuid
from datetime import timedelta, date, datetime, time
from unittest import mock
from django.test import override_settings

import pandas as pd
import pytz
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.db import transaction
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APITestCase
from rest_framework import status

from src.apps.base.tests.factories import EmploymentFactory, WorkerPositionFactory, UserFactory, EmployeeFactory
from src.apps.base.models import Group, WorkerPosition, Employment, Break, ApiLog, SAWHSettings
from src.adapters.celery.tasks import delete_inactive_employment_groups
from src.apps.timetable.models import WorkTypeName, EmploymentWorkType, WorkerDay
from src.apps.timetable.tests.factories import WorkerDayFactory, WorkTypeFactory, EmploymentWorkTypeFactory, WorkTypeNameFactory
from src.common.mixins.tests import TestsHelperMixin
from src.common.models_converter import Converter


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class TestEmploymentAPI(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.break1 = Break.objects.create(
            name='break1',
            network=cls.network,
            value='[[0, 1440, [30, 30]]]',
        )
        cls.sawh_settings = SAWHSettings.objects.create(
            name='5/2, 8ч',
            code='5/2, 8h',
            network=cls.network,
            type=SAWHSettings.PART_OF_PROD_CAL_SUMM
        )
        cls.worker_position = WorkerPosition.objects.create(
            name='Директор магазина',
            code='director',
            network=cls.network,
            breaks=cls.break1,
            sawh_settings=cls.sawh_settings
        )
        cls.break2 = Break.objects.create(
            name='break2',
            network=cls.network,
            value='[[0, 1440, [30]]]',
        )
        cls.another_worker_position = WorkerPosition.objects.create(
            name='Заместитель директора магазина',
            network=cls.network,
            breaks=cls.break2,
            code='deputy director',
        )
        cls.wt_name = WorkTypeName.objects.create(name='test_name', code='test_code', network=cls.network)
        cls.wt_name2 = WorkTypeName.objects.create(name='test_name2', code='test_code2', network=cls.network)
        cls.worker_position.default_work_type_names.set([cls.wt_name, cls.wt_name2])
        cls.dt_now = timezone.now().date()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)
        self.employment2.shop.network.refresh_from_db()
        self.user1.network.refresh_from_db()

    def _create_employment(self):
        data = {
            'position_id': self.worker_position.id,
            'dt_hired': (timezone.now() - timedelta(days=500)).strftime('%Y-%m-%d'),
            'shop_id': self.shop.id,
            'employee_id': self.employee2.id,
            'tabel_code': None,
        }

        resp = self.client.post(
            self.get_url('Employment-list'), data=self.dump_data(data), content_type='application/json')
        return resp

    def test_work_types_added_on_employment_creation(self):
        resp = self._create_employment()
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        empl_qs = EmploymentWorkType.objects.filter(employment_id=resp_data['id'])
        for wtn in [self.wt_name, self.wt_name2]:
            self.assertTrue(empl_qs.filter(
                work_type__work_type_name=wtn,
            ).exists())
        
        self.assertEqual(empl_qs.filter(priority=1).count(), 1)
        self.assertEqual(empl_qs.filter(priority=0).count(), 1)

    def test_work_types_updated_on_position_change(self):
        another_worker_position = WorkerPosition.objects.create(
            name='Заместитель директора магазина',
            network=self.network,
        )
        another_wt_name = WorkTypeName.objects.create(
            name='test_another_name', 
            code='test_another_code', 
            network=self.network,
        )
        another_worker_position.default_work_type_names.add(another_wt_name)
        put_data = {
            'position_id': another_worker_position.id,
            'shop_id': self.shop.id,
            'employee_id': self.employee2.id,
            'dt_hired': (timezone.now() - timedelta(days=200)).strftime('%Y-%m-%d'),
        }
        self.assertFalse(EmploymentWorkType.objects.filter(employment=self.employment2).exists())
        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=self.employment2.id),
            data=self.dump_data(put_data), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json().get('work_types'))
        self.assertTrue(EmploymentWorkType.objects.filter(
            employment=self.employment2,
            work_type__work_type_name=another_wt_name,
        ).exists())

    def test_put_create_employment(self):
        """
        change PUT logic of employment for orteka
        :return:
        """

        put_data = {
            'position_id': self.worker_position.id,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
            'shop_id': self.shop2.id,
            'employee_id': self.employee2.id,
            'dt_fired': None,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk='not_used'),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Employment.objects.filter(
            shop_id=put_data['shop_id'],
            dt_hired=put_data['dt_hired'],
            employee_id=put_data['employee_id'],
            position_id=put_data['position_id'],
        ).count() == 1)

    def test_update_employment_norm_work_hours(self):
        """
        change PUT logic of employment for orteka
        :return:
        """

        put_data = {
            'position_id': self.worker_position.id,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
            'shop_id': self.shop2.id,
            'employee_id': self.employee2.id,
            'norm_work_hours': 123.0,
        }

        resp = self._create_employment()
        self.assertEqual(resp.status_code, 201)
        employment_id = resp.json()['id']

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=employment_id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Employment.objects.filter(
            shop_id=put_data['shop_id'],
            dt_hired=put_data['dt_hired'],
            employee_id=put_data['employee_id'],
            position_id=put_data['position_id'],
        ).first().norm_work_hours, 123.0)

    def test_put_by_code(self):
        self.network.set_settings_value("api_log_settings", {
            "delete_gap_days": 90,
            "log_funcs": {
                "Employment": {
                    "by_code": True,
                    "http_methods": ['POST', 'PUT'],
                    "save_response_codes": [400],
                }
            }
        })

        self.shop2.code = str(self.shop2.id)
        self.shop2.save()
        self.user2.username = f'u-{self.user2.id}'
        self.user2.save()

        empl_code = f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}'
        put_data = {
            'position_code': self.worker_position.code,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
            'dt_fired': (timezone.now() + timedelta(days=300)).strftime('%Y-%m-%d'),
            'shop_code': self.shop2.code,
            'username': self.user2.username,
            'code': empl_code,
            'tabel_code': self.employee2.tabel_code,
            'by_code': True,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=empl_code),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)  # created
        self.assertIsNotNone(resp.json().get('work_types'))
        e = Employment.objects.filter(
            code=empl_code,
            shop_id=self.shop2.id,
            dt_hired=put_data['dt_hired'],
            dt_fired=put_data['dt_fired'],
            employee_id=self.employee2.id,
            position_id=self.worker_position.id
        ).first()
        self.assertIsNotNone(e)

        put_data['dt_fired'] = timezone.now().strftime('%Y-%m-%d')
        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=empl_code),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)  # updated
        e = Employment.objects.filter(
            code=empl_code,
            shop_id=self.shop2.id,
            dt_hired=put_data['dt_hired'],
            dt_fired=put_data['dt_fired'],
            employee_id=self.employee2.id,
            position_id=self.worker_position.id,
        ).first()
        self.assertIsNotNone(e)

        self.shop3.code = str(self.shop3.id)
        self.shop3.save()
        put_data['shop_code'] = self.shop3.code
        put_data['tabel_code'] = 'new_tabel_code'
        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=empl_code),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)  # updated
        e.refresh_from_db(fields=['shop', 'employee'])
        self.assertEqual(e.shop.id, self.shop3.id)
        self.assertEqual(e.employee.tabel_code, self.employee2.tabel_code)  # cant change tabel_code for existing employment
        
        self.assertEqual(ApiLog.objects.count(), 3)

    def test_auto_timetable(self):
        Employment.objects.all().update(auto_timetable=True)
        employment_ids = list(Employment.objects.filter(shop=self.shop).values_list('id', flat=True))
        employment_ids = employment_ids[1:-2]

        self.assertEqual(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=True).count(), 5)
        data = {
            "employment_ids": employment_ids,
            "auto_timetable": False,
        }
        response = self.client.post('/rest_api/employment/auto_timetable/', data=self.dump_data(data),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=False).count(), 2)
        self.assertEqual(list(
            Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=False).values_list('id', flat=True).order_by('id')),
            sorted(employment_ids))

    def test_work_hours_change_on_update_position(self):
        dt = date.today()
        resp = self._create_employment().json()
        for i in range(3):
            WorkerDay.objects.create(
                employment_id=resp['id'],
                employee=self.employee2,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt + timedelta(i), time(10)),
                dttm_work_end=datetime.combine(dt + timedelta(i), time(20)),
                shop=self.shop,
                dt=dt + timedelta(i),
            )
        for i in range(2):
            WorkerDay.objects.create(
                employment_id=resp['id'],
                employee=self.employee2,
                dt=dt + timedelta(i + 3),
                type_id=WorkerDay.TYPE_EMPTY,
            )
        self.assertEqual(WorkerDay.objects.get(employment_id=resp['id'], dt=dt).work_hours, timedelta(hours=9))
        self.assertEqual(WorkerDay.objects.get(employment_id=resp['id'], dt=dt + timedelta(1)).work_hours,
                         timedelta(hours=9))
        emp = Employment.objects.get(pk=resp['id'])
        emp.position = self.another_worker_position
        emp.save()
        self.assertEqual(WorkerDay.objects.get(employment_id=resp['id'], dt=dt).work_hours, timedelta(hours=9))
        self.assertEqual(WorkerDay.objects.get(employment_id=resp['id'], dt=dt + timedelta(1)).work_hours,
                         timedelta(hours=9, minutes=30))

    def _test_get_empls(self, extra_params=None, check_length=None):
        params = {
            'dt_from': Converter.convert_date(self.dt_now),
            'dt_to': Converter.convert_date(self.dt_now),
        }

        if extra_params:
            params.update(extra_params)

        resp = self.client.get(path=self.get_url('Employment-list'), data=params)

        if check_length:
            self.assertEqual(len(resp.json()), check_length)

        return resp

    def test_get_mine_employments(self):
        self._test_get_empls(check_length=8)
        self._test_get_empls(extra_params={'mine': True}, check_length=8)

        self.client.force_authenticate(user=self.user2)
        self._test_get_empls(extra_params={'mine': True}, check_length=5)

        self.client.force_authenticate(user=self.user5)
        self._test_get_empls(extra_params={'mine': True}, check_length=7)

        self.client.force_authenticate(user=self.user8)
        self._test_get_empls(check_length=8)
        self._test_get_empls(extra_params={'mine': True}, check_length=1)

    @mock.patch.object(transaction, 'on_commit', lambda t: t())
    def test_empls_cleaned_in_wdays_without_active_employment(self):
        dt = datetime.now().date()
        self.employment2.employee.user.network.clean_wdays_on_employment_dt_change = True
        self.employment2.employee.user.network.save()

        wd1 = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt + timedelta(days=50),
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(dt, time(20, 0, 0)),
            is_approved=True,
        )
        wd2 = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt + timedelta(days=25),
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(dt, time(20, 0, 0)),
            is_approved=True,
        )
        wd_holiday = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt + timedelta(days=20),
            is_fact=False,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_approved=True,
        )
        wd_count_before_save = WorkerDay.objects.count()
        self.employment2.dt_hired = dt
        self.employment2.dt_fired = dt + timedelta(days=30)
        self.employment2.save()
        self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd1.id).exists())
        wd1.refresh_from_db()
        self.assertIsNone(wd1.employment_id)
        self.assertTrue(WorkerDay.objects.filter(id=wd2.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=wd_holiday.id).exists())
        self.assertEqual(WorkerDay.objects_with_excluded.count(), wd_count_before_save)

    def test_change_function_group_tmp(self):
        self.admin_group.subordinates.add(self.chief_group)
        self.admin_group.subordinates.add(self.employee_group)

        put_data = {
            'function_group_id': self.chief_group.id,
            'dt_to_function_group': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=self.employment2.id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.json()['function_group_id'], self.chief_group.id)
        self.assertEqual(resp.json()['dt_to_function_group'], (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'))

    def test_change_function_group_tmp_through_position(self):
        self.admin_group.subordinates.add(self.chief_group)
        self.admin_group.subordinates.add(self.employee_group)
        self.worker_position.group = self.admin_group
        self.worker_position.save()
        self.employment1.function_group_id = None
        self.employment1.position = self.worker_position
        self.employment1.save()
        put_data = {
            'function_group_id': self.chief_group.id,
            'dt_to_function_group': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=self.employment2.id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.json()['function_group_id'], self.chief_group.id)
        self.assertEqual(resp.json()['dt_to_function_group'], (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'))

    def test_delete_function_group_tmp(self):
        self.admin_group.subordinates.add(self.chief_group)
        self.admin_group.subordinates.add(self.employee_group)
        put_data = {
            'function_group_id': None,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=self.employment2.id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertIsNone(resp.json()['function_group_id'])

    def test_change_function_group_tmp_no_perm(self):
        self.admin_group.subordinates.clear()
        self.admin_group.subordinates.add(self.employee_group)
        put_data = {
            'function_group_id': self.chief_group.id,
            'dt_to_function_group': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=self.employment2.id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_delete_inactive_function_groups(self):
        self.employment2.dt_to_function_group = date.today() - timedelta(days=5)
        self.employment2.save()
        delete_inactive_employment_groups()
        self.assertIsNone(Employment.objects.get(id=self.employment2.id).function_group_id)
        self.assertIsNotNone(Employment.objects.get(id=self.employment1.id).function_group_id)

    def test_timetable_permissions(self):
        data = {
            'dt_fired': '2020-10-10',
            'position_id': self.worker_position.id,
            'is_fixed_hours': True,
            'is_visible': False,
        }
        response = self.client.put(f'/rest_api/employment/{self.employment3.id}/timetable/', data=self.dump_data(data),
                                   content_type='application/json')
        data = {
            'is_fixed_hours': True,
            'salary': '150.00',
            'week_availability': 7,
            'norm_work_hours': 100.0,
            'min_time_btw_shifts': None,
            'shift_hours_length_min': None,
            'shift_hours_length_max': None,
            'is_ready_for_overworkings': False,
            'is_visible_other_shops': True,
            'is_visible': False,
            'function_group_id': self.employee_group.id,
        }
        self.assertEqual(response.json(), data)
        self.employment3.refresh_from_db()
        self.assertIsNone(self.employment3.position_id)
        self.assertIsNone(self.employment3.dt_fired)

    def test_not_descreased_employment_dt_hired_if_setting_is_enabled_and_not_by_code(self):
        self.user1.network.descrease_employment_dt_fired_in_api = True
        self.user1.network.save()

        put_data = {
            'position_id': self.worker_position.id,
            'dt_hired': date(2021, 1, 1),
            'dt_fired': date(2021, 5, 25),
            'shop_id': self.shop2.id,
            'employee_id': self.employee2.id,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk='not_used'),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Employment.objects.filter(
            shop_id=put_data['shop_id'],
            dt_hired=put_data['dt_hired'],
            dt_fired=put_data['dt_fired'],
            employee_id=put_data['employee_id'],
            position_id=put_data['position_id'],
        ).count() == 1)

    def test_descrease_employment_dt_hired_if_setting_is_enabled_and_by_code(self):
        self.user1.network.descrease_employment_dt_fired_in_api = True
        self.user1.network.save()

        put_data = {
            'by_code': True,
            'position_code': self.worker_position.code,
            'dt_hired': date(2021, 1, 1),
            'dt_fired': date(2021, 5, 25),
            'shop_code': self.shop2.code,
            'username': self.employee2.user.username,
            'tabel_code': self.employee2.tabel_code,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk='not_used'),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Employment.objects.filter(
            shop_id=self.shop2.id,
            dt_hired=date(2021, 1, 1),
            dt_fired=date(2021, 5, 24),
            employee_id=self.employee2.id,
            position_id=self.worker_position.id,
        ).count() == 1)

    def test_delete_employment_by_code(self):
        """
        создание 2 одновременно активных трудоустройств для 1 пользователя
        создание рабочих дней для одного из трудоустройств
        удаление одного из трудоустройств -> рабочие дни должны перекрепиться на другое активное трудоустройство
        # TODO: правильна ли такая логика для случая, когда логин пользователя не табельный номер (нужна настройка?)
        """
        self.network.clean_wdays_on_employment_dt_change = True
        self.network.save()

        put_data1 = {
            'position_id': self.worker_position.id,
            'dt_hired': date(2021, 1, 1).strftime('%Y-%m-%d'),
            'dt_fired': date(2021, 5, 25).strftime('%Y-%m-%d'),
            'shop_id': self.shop2.id,
            'employee_id': self.employee2.id,
            'code': 'code1',
            'by_code': True,
        }
        resp1_put = self.client.put(
            path=self.get_url('Employment-detail', 'code1'),
            data=self.dump_data(put_data1),
            content_type='application/json',
        )
        self.assertEqual(resp1_put.status_code, 201)
        empl1 = Employment.objects.get(id=resp1_put.json()['id'])
        self.assertEqual(empl1.code, 'code1')
        put_data2 = {
            'position_id': self.worker_position.id,
            'dt_hired': date(2021, 1, 1).strftime('%Y-%m-%d'),
            'dt_fired': date(2021, 5, 25).strftime('%Y-%m-%d'),
            'shop_id': self.shop2.id,
            'employee_id': self.employee2.id,
            'code': 'code2',
            'by_code': True,
        }
        resp2_put = self.client.put(
            path=self.get_url('Employment-detail', 'code2'),
            data=self.dump_data(put_data2),
            content_type='application/json',
        )
        self.assertEqual(resp2_put.status_code, 201)
        empl2 = Employment.objects.get(id=resp2_put.json()['id'])
        self.assertEqual(empl2.code, 'code2')

        wd = WorkerDayFactory(
            dt=date(2021, 1, 1),
            employee=self.employee2,
            employment=empl1,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
        )

        resp2_delete = self.client.delete(
            path=self.get_url('Employment-detail', 'code2'),
            data=self.dump_data({'by_code': True}),
            content_type='application/json',
        )
        self.assertEqual(resp2_delete.status_code, 204)
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, empl1.id)

        # при повтором put для empl с тем же code -- признак удаленности должен пропасть
        resp2_put2 = self.client.put(
            path=self.get_url('Employment-detail', 'code2'),
            data=self.dump_data(put_data2),
            content_type='application/json',
        )
        self.assertEqual(resp2_put2.status_code, 200)
        empl2.refresh_from_db()
        self.assertEqual(empl2.dttm_deleted, None)

    def test_delete_employment_with_filter_delete(self):
        """
        Проверка, что при удалении через objects.filter(...).delete() тоже чистятся дни
        """
        put_data1 = {
            'position_id': self.worker_position.id,
            'dt_hired': date(2021, 1, 1).strftime('%Y-%m-%d'),
            'dt_fired': date(2021, 5, 25).strftime('%Y-%m-%d'),
            'shop_id': self.shop2.id,
            'employee_id': self.employee2.id,
            'code': 'code1',
            'by_code': True,
        }
        resp1_put = self.client.put(
            path=self.get_url('Employment-detail', 'code1'),
            data=self.dump_data(put_data1),
            content_type='application/json',
        )
        self.assertEqual(resp1_put.status_code, 201)
        empl1 = Employment.objects.get(id=resp1_put.json()['id'])
        wd = WorkerDayFactory(
            dt=date(2021, 1, 1),
            employee=self.employee2,
            employment=empl1,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
        )
        Employment.objects.filter(id=empl1.id).delete()
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, None)

    def _test_get_employment_ordered_by_position(self, ordering):
        self.wp1 = WorkerPosition.objects.create(
            name='Администатор',
            network=self.network,
            ordering=1,
        )
        self.wp2 = WorkerPosition.objects.create(
            name='Директор',
            network=self.network,
            ordering=2,
        )
        self.wp3 = WorkerPosition.objects.create(
            name='Уборщик',
            network=self.network,
        )
        self.wp4 = WorkerPosition.objects.create(
            name='Кассир',
            network=self.network,
        )
        self.wp5 = WorkerPosition.objects.create(
            name='Провизор',
            network=self.network,
        )
        self.employment2.position = self.wp1
        self.employment3.position = self.wp2
        self.employment4.position = self.wp3
        self.employment6.position = self.wp4
        self.employment7.position = self.wp5
        self.employment2.save()
        self.employment3.save()
        self.employment4.save()
        self.employment6.save()
        self.employment7.save()
        
        return self.client.get(f'/rest_api/employment/?shop_id={self.shop.id}&order_by={ordering}')

    def test_get_employment_ordered_by_position_asc(self):
        data = self._test_get_employment_ordered_by_position(ordering='position__ordering,position__name')
        assert_data = [
            (self.user2.id, self.wp1.id),
            (self.user3.id, self.wp2.id),
            (self.user6.id, self.wp4.id),
            (self.user7.id, self.wp5.id),
            (self.user4.id, self.wp3.id),
        ]
        self.assertSequenceEqual(list(map(lambda x: (x['user_id'], x['position_id']), data.json())), assert_data)

    def test_get_employment_ordered_by_position_desc(self):
        data = self._test_get_employment_ordered_by_position(ordering='-position__ordering,position__name')
        assert_data = [
            (self.user6.id, self.wp4.id),
            (self.user7.id, self.wp5.id),
            (self.user4.id, self.wp3.id),
            (self.user3.id, self.wp2.id),
            (self.user2.id, self.wp1.id),
        ]
        self.assertSequenceEqual(list(map(lambda x: (x['user_id'], x['position_id']), data.json())), assert_data)

    def test_employment_work_type_validation(self):
        resp = self._create_employment()
        self.assertEqual(resp.status_code, 201)
        employment_id = resp.json()['id']
        employment_work_type = EmploymentWorkType.objects.filter(employment_id=employment_id).first()
        work_type_id = employment_work_type.work_type_id
        data = {
            'employment_id': employment_id,
            'work_type_id': work_type_id,
        }
        response = self.client.post(
            '/rest_api/employment_work_type/', 
            data=self.dump_data(data),
            content_type='application/json',
        )
        self.assertEqual(response.json(), {'non_field_errors': ['Поля work_type_id, employment_id должны производить массив с уникальными значениями.']})
        EmploymentWorkType.objects.filter(employment_id=employment_id, work_type_id=work_type_id).update(priority=1)
        empl_work_type_to_create = EmploymentWorkType.objects.filter(employment_id=employment_id).exclude(work_type_id=work_type_id).first()
        empl_work_type_to_create.delete()
        data['work_type_id'] = empl_work_type_to_create.work_type_id
        data['priority'] = 1
        response = self.client.post(
            '/rest_api/employment_work_type/', 
            data=self.dump_data(data),
            content_type='application/json',
        )
        self.assertEqual(response.json(), {'non_field_errors': ['У трудойстройства может быть только один основной тип работ.']})
        data['priority'] = 0
        response = self.client.post(
            '/rest_api/employment_work_type/', 
            data=self.dump_data(data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        item_id = response.json()['id']
        data['priority'] = 1
        response = self.client.put(
            f'/rest_api/employment_work_type/{item_id}/', 
            data=self.dump_data(data),
            content_type='application/json',
        )
        self.assertEqual(response.json(), {'non_field_errors': ['У трудойстройства может быть только один основной тип работ.']})
        data['work_type_id'] = work_type_id
        response = self.client.put(
            f'/rest_api/employment_work_type/{employment_work_type.id}/', 
            data=self.dump_data(data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_ignore_shop_code_when_updating_employment_via_api(self):
        self.network.ignore_shop_code_when_updating_employment_via_api = True
        self.network.save()

        self.shop2.code = str(self.shop2.id)
        self.shop2.save()
        self.user2.username = f'u-{self.user2.id}'
        self.user2.save()

        empl_code = f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}'
        put_data = {
            'position_code': self.worker_position.code,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
            'dt_fired': (timezone.now() + timedelta(days=300)).strftime('%Y-%m-%d'),
            'shop_code': self.shop2.code,
            'username': self.user2.username,
            'code': empl_code,
            'tabel_code': self.employee2.tabel_code,
            'by_code': True,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=empl_code),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)  # created

        put_data['shop_code'] = self.shop3.code
        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=empl_code),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        employment = Employment.objects.get(id=resp.json()['id'])
        self.assertEqual(employment.shop_id, self.shop2.id)

    def _test_update_worker_position_permissions(self, position_id, status_code, assert_position_id):
        response = self.client.put(
            f'/rest_api/employment/{self.employment3.id}/', 
            data=self.dump_data(
                {
                    'position_id': position_id,
                    'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
                    'shop_id': self.shop2.id,
                    'employee_id': self.employee2.id,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, status_code)
        self.employment3.refresh_from_db()
        self.assertEqual(self.employment3.position_id, assert_position_id)

    def test_update_worker_position_permissions(self):
        self.admin_group.subordinates.clear()
        self.employment3.worker_position = None
        self.employment3.save()
        worker_position_with_chief_group = WorkerPosition.objects.create(
            name='worker_position_with_chief_group',
            network=self.network,
            group=self.chief_group,
        )
        worker_position_with_employee_group = WorkerPosition.objects.create(
            name='worker_position_with_employee_group',
            network=self.network,
            group=self.employee_group,
        )
        # нет subordunates
        self._test_update_worker_position_permissions(worker_position_with_chief_group.id, 403, None)
        self.admin_group.subordinates.add(self.chief_group)
        # есть chief_group в subordunates
        self._test_update_worker_position_permissions(worker_position_with_chief_group.id, 200, worker_position_with_chief_group.id)
        # нет employee_group в subordunates
        self._test_update_worker_position_permissions(worker_position_with_employee_group.id, 403, worker_position_with_chief_group.id)
        self.admin_group.subordinates.add(self.employee_group)
        self.admin_group.subordinates.remove(self.chief_group)
        # есть employee_group в subordunates, но нет chief_group в subordunates
        self._test_update_worker_position_permissions(worker_position_with_employee_group.id, 403, worker_position_with_chief_group.id)
        self.admin_group.subordinates.add(self.chief_group)
        # все есть в subordunates
        self._test_update_worker_position_permissions(worker_position_with_employee_group.id, 200, worker_position_with_employee_group.id)
        self.admin_group.subordinates.clear()
        self.employment3.worker_position = None
        self.employment3.save()

    def _test_update_group_permissions(self, group_id, status_code, assert_group_id):
        response = self.client.put(
            f'/rest_api/employment/{self.employment3.id}/', 
            data=self.dump_data(
                {
                    'function_group_id': group_id,
                    'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
                    'shop_id': self.shop2.id,
                    'employee_id': self.employee2.id,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, status_code)
        self.employment3.refresh_from_db()
        self.assertEqual(self.employment3.function_group_id, assert_group_id)

    def test_update_group_permissions(self):
        self.admin_group.subordinates.clear()
        self.employment3.function_group_id = None
        self.employment3.worker_position = None
        self.employment3.save()
        # нет subordunates
        self._test_update_group_permissions(self.chief_group.id, 403, None)
        self.admin_group.subordinates.add(self.chief_group)
        # есть chief_group в subordunates
        self._test_update_group_permissions(self.chief_group.id, 200, self.chief_group.id)
        # нет employee_group в subordunates
        self._test_update_group_permissions(self.employee_group.id, 403, self.chief_group.id)
        self.admin_group.subordinates.add(self.employee_group)
        self.admin_group.subordinates.remove(self.chief_group)
        # есть employee_group в subordunates, но нет chief_group в subordunates
        self._test_update_group_permissions(self.employee_group.id, 403, self.chief_group.id)
        self.admin_group.subordinates.add(self.chief_group)
        # все есть в subordunates
        self._test_update_group_permissions(self.employee_group.id, 200, self.employee_group.id)
        self.admin_group.subordinates.clear()
        # нет subordunates, не можем очистить группу
        self._test_update_group_permissions(None, 403, self.employee_group.id)
        # есть employee_group в subordunates
        self.admin_group.subordinates.add(self.employee_group)
        self._test_update_group_permissions(None, 200, None)
        self.admin_group.subordinates.clear()

    @mock.patch.object(transaction, 'on_commit', lambda t: t())
    def test_batch_update_or_create(self):
        Employment.objects.filter(employee=self.employee2, code__isnull=True).delete()
        now = timezone.now()
        dt_now = now.date()

        options = {
            'by_code': True,
            'delete_scope_fields_list': [
                'employee_id',
            ],
            'delete_scope_filters': {
                'dt_hired__lte': (dt_now + relativedelta(months=1)).replace(day=1),
                'dt_fired__gte_or_isnull': dt_now.replace(day=1),
            }
        }
        data = {
            'data': [
                {
                    'code': 'e_new',
                    'position_code': self.worker_position.code,
                    'dt_hired': (dt_now - timedelta(days=300)).strftime('%Y-%m-%d'),
                    'dt_fired': (dt_now + timedelta(days=300)).strftime('%Y-%m-%d'),
                    'shop_code': self.shop2.code,
                    'username': self.user2.username,
                    'tabel_code': self.employee2.tabel_code,
                    'norm_work_hours': 100,
                },
            ],
            'options': options,
        }

        resp = self.client.post(
            self.get_url('Employment-batch-update-or-create'),
            self.dump_data(data), content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "created": 1,
                        "deleted": 1
                    }
                }
            }
        )

        e_new_employment = Employment.objects.get(code='e_new')
        self.assertEqual(e_new_employment.sawh_settings_id, self.sawh_settings.id)

        # old employment
        o_e = Employment.objects.create(
            code='o_e',
            shop=self.shop2,
            employee=self.employee2,
            position=self.worker_position,
            dt_hired=now - timedelta(days=300),
            dt_fired=now - timedelta(days=100),
        )

        # future employments
        f_e = Employment.objects.create(
            code='f_e',
            shop=self.shop2,
            employee=self.employee2,
            position=self.worker_position,
            dt_hired=now + timedelta(days=100),
            dt_fired=now + timedelta(days=300),
        )
        f_e2 = Employment.objects.create(
            code='f_e2',
            shop=self.shop2,
            employee=self.employee2,
            position=self.worker_position,
            dt_hired=now + timedelta(days=100),
            dt_fired=None,
        )

        # curr empl to delete
        d_e = Employment.objects.create(
            code='d_e',
            shop=self.shop2,
            employee=self.employee2,
            position=self.worker_position,
            dt_hired=now,
            dt_fired=None,
        )
        wd = WorkerDayFactory(
            dt=dt_now,
            employee=self.employee2,
            employment=d_e,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
        )

        # curr empl without code to skip
        s_e = Employment.objects.create(
            shop=self.shop2,
            employee=self.employee2,
            position=self.worker_position,
            dt_hired=now,
            dt_fired=None,
            norm_work_hours=0,
        )
        d_e.refresh_from_db()
        self.assertTrue(Employment.objects.filter(id=d_e.id).exists())
        resp = self.client.post(
            self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "deleted": 1,
                        "skipped": 1
                    }
                }
            }
        )
        self.assertTrue(Employment.objects.filter(id=o_e.id).exists())
        self.assertTrue(Employment.objects.filter(id=f_e.id).exists())
        self.assertTrue(Employment.objects.filter(id=f_e2.id).exists())
        self.assertTrue(Employment.objects.filter(id=s_e.id).exists())
        self.assertFalse(Employment.objects.filter(id=d_e.id).exists())
        deleted_wd = WorkerDay.objects_with_excluded.filter(id=wd.id).first()
        self.assertNotEqual(deleted_wd.employment_id, d_e.id)
        self.assertEqual(deleted_wd.employment.code, 'e_new')

        self.employee3.tabel_code = 'employee3'
        self.employee3.save()

        self.employment3.dt_hired = date(2021, 11, 1)
        self.employment3.dt_fired = date(3999, 12, 31)
        self.employment3.position = self.worker_position
        self.employment3.code = 'current_employment3'
        self.employment3.save()

        self.network.clean_wdays_on_employment_dt_change = True
        self.network.save()

        future_plan_worker_day = WorkerDayFactory(
            employee=self.employee3,
            employment=self.employment3,
            dt=dt_now + timedelta(1),
            dttm_work_start=datetime.combine(dt_now + timedelta(1), time(8)),
            dttm_work_end=datetime.combine(dt_now + timedelta(1), time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            is_approved=True,
            is_fact=False,
        )

        self.assertEqual(future_plan_worker_day.work_hours, timedelta(hours=11))

        data = {
            'data': [
                {
                    'code': 'new_employment3',
                    'position_code': self.worker_position.code,
                    'dt_hired': (dt_now + timedelta(days=1)).strftime('%Y-%m-%d'),
                    'dt_fired': date(3999, 12, 31).strftime('%Y-%m-%d'),
                    'shop_code': self.shop.code,
                    'username': self.user3.username,
                    'tabel_code': self.employee3.tabel_code,
                },
                {
                    'code': 'current_employment3',
                    'position_code': self.another_worker_position.code,
                    'dt_hired': date(2021, 11, 1).strftime('%Y-%m-%d'),
                    'dt_fired': dt_now.strftime('%Y-%m-%d'),
                    'shop_code': self.shop.code,
                    'username': self.user3.username,
                    'tabel_code': self.employee3.tabel_code,
                },
            ],
            'options': options,
        }
        
        resp = self.client.post(
            self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "created": 1,
                        "updated": 1
                    }
                }
            }
        )
        self.employment3.refresh_from_db()
        created_empl = Employment.objects.get(code='new_employment3')
        self.assertEqual(self.employment3.dt_fired, dt_now)
        self.assertEqual(created_empl.dt_hired, dt_now + timedelta(1))
        self.assertEqual(created_empl.dt_fired, date(3999, 12, 31))
        self.assertEqual(EmploymentWorkType.objects.filter(employment=created_empl).count(), 2)
        future_plan_worker_day.refresh_from_db()
        self.assertEqual(future_plan_worker_day.work_hours, timedelta(hours=11, minutes=30))
        self.assertEqual(future_plan_worker_day.employment_id, created_empl.id)

        # restore "deleted" employment
        employment = Employment.objects.filter(code='new_employment3').first()
        employment.delete()
        self.assertIsNotNone(employment.dttm_deleted)
        resp = self.client.post(
            self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "skipped": 1,
                        "updated": 1
                    }
                }
            }
        )
        employment.refresh_from_db()
        self.assertIsNone(employment.dttm_deleted)

    def test_batch_update_or_create_diff_report(self):
        dt_now = date(2021, 12, 6)

        options = {
            'by_code': True,
            'delete_scope_fields_list': [
                'employee_id',
            ],
            'delete_scope_filters': {
                'dt_hired__lte': (dt_now + relativedelta(months=1)).replace(day=1) - timedelta(days=1),
                'dt_fired__gte_or_isnull': dt_now.replace(day=1),
            },
            'diff_report_email_to': ['dummy@example.com']
        }
        data = {
            'data': [
                {
                    'code': 'e_new',
                    'position_code': self.worker_position.code,
                    'dt_hired': (dt_now - timedelta(days=300)).strftime('%Y-%m-%d'),
                    'dt_fired': (dt_now + timedelta(days=300)).strftime('%Y-%m-%d'),
                    'shop_code': self.shop2.code,
                    'username': self.user2.username,
                    'tabel_code': self.employee2.tabel_code,
                },
            ],
            'options': options,
        }

        dttm1 = datetime(2021, 12, 9, 10, 1, 3)
        with freeze_time(dttm1):
            resp = self.client.post(
                self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "created": 1,
                        "deleted": 1
                    }
                }
            }
        )

        dttm2 = datetime(2021, 12, 9, 12, 3, 3)
        with freeze_time(dttm2):
            resp = self.client.post(
                self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "skipped": 1,
                    }
                }
            }
        )

        dttm3 = datetime(2021, 12, 9, 13, 3, 3)
        data['data'][0]['dt_fired'] = (dt_now + timedelta(days=900)).strftime('%Y-%m-%d')
        with freeze_time(dttm3):
            resp = self.client.post(
                self.get_url('Employment-batch-update-or-create'), self.dump_data(data),
                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "updated": 1,
                    }
                }
            }
        )

        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(mail.outbox[0].subject, 'Сверка трудоустройств от 2021-12-09T10:01:03')
        self.assertEqual(mail.outbox[0].body, 'Создано: 1, Удалено: 1, Изменено: 0, Пропущено: 0')
        self.assertEqual(mail.outbox[1].subject, 'Сверка трудоустройств от 2021-12-09T12:03:03')
        self.assertEqual(mail.outbox[1].body, 'Создано: 0, Удалено: 0, Изменено: 0, Пропущено: 1')
        self.assertEqual(mail.outbox[2].subject, 'Сверка трудоустройств от 2021-12-09T13:03:03')
        self.assertEqual(mail.outbox[2].body, 'Создано: 0, Удалено: 0, Изменено: 1, Пропущено: 0')
        attachment1 = mail.outbox[0].attachments[0][1]
        df_created = pd.read_excel(attachment1, dtype=str, sheet_name='Создано')
        df_deleted = pd.read_excel(attachment1, dtype=str, sheet_name='Удалено')
        df_before_update = pd.read_excel(attachment1, dtype=str, sheet_name='До изменений')
        df_after_update = pd.read_excel(attachment1, dtype=str, sheet_name='После изменений')
        df_skipped = pd.read_excel(attachment1, dtype=str, sheet_name='Пропущено')
        self.assertEqual(len(df_created.index), 1)
        self.assertEqual(len(df_deleted.index), 1)
        self.assertEqual(len(df_before_update.index), 0)
        self.assertEqual(len(df_after_update.index), 0)
        self.assertEqual(len(df_skipped.index), 0)

        attachment2 = mail.outbox[1].attachments[0][1]
        df_created = pd.read_excel(attachment2, dtype=str, sheet_name='Создано')
        df_deleted = pd.read_excel(attachment2, dtype=str, sheet_name='Удалено')
        df_before_update = pd.read_excel(attachment2, dtype=str, sheet_name='До изменений')
        df_after_update = pd.read_excel(attachment2, dtype=str, sheet_name='После изменений')
        df_skipped = pd.read_excel(attachment2, dtype=str, sheet_name='Пропущено')
        self.assertEqual(len(df_created.index), 0)
        self.assertEqual(len(df_deleted.index), 0)
        self.assertEqual(len(df_before_update.index), 0)
        self.assertEqual(len(df_after_update.index), 0)
        self.assertEqual(len(df_skipped.index), 1)

        attachment3 = mail.outbox[2].attachments[0][1]
        df_created = pd.read_excel(attachment3, dtype=str, sheet_name='Создано')
        df_deleted = pd.read_excel(attachment3, dtype=str, sheet_name='Удалено')
        df_before_update = pd.read_excel(attachment3, dtype=str, sheet_name='До изменений')
        df_after_update = pd.read_excel(attachment3, dtype=str, sheet_name='После изменений')
        df_skipped = pd.read_excel(attachment3, dtype=str, sheet_name='Пропущено')
        self.assertEqual(len(df_created.index), 0)
        self.assertEqual(len(df_deleted.index), 0)
        self.assertEqual(len(df_before_update.index), 1)
        self.assertEqual(len(df_after_update.index), 1)
        self.assertEqual(len(df_skipped.index), 0)
        self.assertTrue(df_before_update['ДатаОкончанияРаботы'][0].startswith('2022-10-02'))
        self.assertTrue(df_after_update['ДатаОкончанияРаботы'][0].startswith('2024-05-24'))

    def test_batch_update_or_create_dry_run(self):
        employments_count_before = Employment.objects.filter(code__isnull=False).count()
        dt_now = date(2021, 12, 6)

        options = {
            'by_code': True,
            'delete_scope_fields_list': [
                'employee_id',
            ],
            'delete_scope_filters': {
                'dt_hired__lte': (dt_now + relativedelta(months=1)).replace(day=1) - timedelta(days=1),
                'dt_fired__gte_or_isnull': dt_now.replace(day=1),
            },
            'dry_run': True,
        }
        data = {
            'data': [
                {
                    'code': 'e_new',
                    'position_code': self.worker_position.code,
                    'dt_hired': (dt_now - timedelta(days=300)).strftime('%Y-%m-%d'),
                    'dt_fired': (dt_now + timedelta(days=300)).strftime('%Y-%m-%d'),
                    'shop_code': self.shop2.code,
                    'username': self.user2.username,
                    'tabel_code': self.employee2.tabel_code,
                },
            ],
            'options': options,
        }

        resp = self.client.post(
            self.get_url('Employment-batch-update-or-create'), self.dump_data(data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "created": 1,
                        "deleted": 1
                    }
                }
            }
        )

        employments_count_after = Employment.objects.filter(code__isnull=False).count()
        self.assertEqual(employments_count_before, employments_count_after)
        self.assertFalse(Employment.objects.filter(code='e_new').exists())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @mock.patch.object(transaction, 'on_commit', lambda t: t())
    def test_batch_update_or_create_related_employee_and_user(self):
        """Employee should be updated/created (by tabel_code or user), User should not be created/updated - throws an error."""
        user1 = UserFactory(username='username1')
        user2 = UserFactory(username='username2')
        employee = EmployeeFactory(user=user1, tabel_code='tabel_code1')
        employment = EmploymentFactory(employee=employee, code='code1')
        data = {
            "data": [
                {
                    "code": "code1",
                    "shop_code": self.shop.code,
                    "position_code": self.worker_position.code,
                    "username": user2.username,
                    "dt_hired": self.dt_now,
                    "dt_fired": self.dt_now + timedelta(10),
                    "tabel_code": employee.tabel_code,
                }
            ],
            "options": {"by_code": True, "delete_scope_fields_list": ["employee_id"]}
        }
        # Employee
        resp = self.client.post(self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(
            resp.json(),
            {
                "stats": {
                    "Employment": {
                        "updated": 1
                    }
                }
            }
        )
        employment = Employment.objects.select_related('employee__user').get(code='code1')
        self.assertEqual(employment.employee_id, employee.id)
        self.assertEqual(employment.employee.user.id, user2.id)

        # User
        username = 'not_a_real_user'
        data['data'][0]['username'] = username
        resp = self.client.post(self.get_url('Employment-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertContains(resp, username, status_code=400)

    def test_has_permission_through_position_when_group_set(self):
        position = WorkerPosition.objects.create(
            name='Test position',
            group=self.admin_group,
            network=self.network,
        )
        group_without_perms = Group.objects.create(
            name='group_without_perms',
            network=self.network,
        )
        self.employment1.function_group = group_without_perms
        self.employment1.position = None
        self.employment1.save()
        response = self.client.get('/rest_api/department/')
        self.assertEqual(response.status_code, 403)
        self.employment1.position = position
        self.employment1.save()
        response = self.client.get('/rest_api/department/')
        self.assertEqual(response.status_code, 200)

    def test_worker_day_restored_after_employment_creation(self):
        self.network.clean_wdays_on_employment_dt_change = True
        self.network.save()
        wd = WorkerDayFactory(
            dt=date(2021, 1, 1),
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
        )
        Employment.objects.delete()
        wd.refresh_from_db()
        self.assertIsNone(wd.employment_id)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            e = Employment.objects.create(
                shop=self.shop,
                employee=self.employee2,
                function_group=self.employee_group,
            )
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, e.id)

    def test_worker_day_reattachment_to_employment_in_batch_update_or_create_bug(self):
        """
        1C integration bug. If you first delete an existing `Employment` (`dttm_deleted` is added),
        attached `WorkerDay`s are left hanging. If you then create the same `Employment` (`dttm_deleted=None` on the same instance),
        the WorkerDays are not reattached, since models fields `dt_fired`, `dt_hired` are not updated.
        """
        empl1 = self.employment1
        empl1.position = WorkerPositionFactory()
        empl1.save()
        empl2 = EmploymentFactory(
            code='empl2',
            employee=empl1.employee,
            shop=empl1.shop,
            position=empl1.position,
            dt_hired=self.dt_now,
            function_group=empl1.function_group
        )
        wd = WorkerDayFactory(
            employment = empl2,
            employee = empl2.employee,
            dt = self.dt_now,
            type_id=WorkerDay.TYPE_WORKDAY
        )
        self.assertTrue(wd.employment)
        data = {
            "data":
                [
                    {
                        "code": empl1.code,
                        "shop_code": empl1.shop.code,
                        "position_code": empl1.position.code,
                        "username": empl1.employee.user.username,
                        "dt_hired": empl1.dt_hired,
                        "norm_work_hours": 100
                    }
                ],
            "options": {"by_code": True, "delete_scope_fields_list": ["employee_id"], "dry_run": False}
        }
        res = self.client.post(self.get_url('Employment-batch-update-or-create'), data, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        wd.refresh_from_db()
        self.assertFalse(wd.employment)

        data = {
            "data":
                [
                    {
                        "code": empl1.code,
                        "shop_code": empl1.shop.code,
                        "position_code": empl1.position.code,
                        "username": empl1.employee.user.username,
                        "dt_hired": empl1.dt_hired,
                        "dt_fired": self.dt_now - timedelta(1),
                        "norm_work_hours": 100
                    },
                    {
                        "code": empl2.code,
                        "shop_code": empl2.shop.code,
                        "position_code": empl2.position.code,
                        "username": empl2.employee.user.username,
                        "dt_hired": self.dt_now,
                        "norm_work_hours": 100
                    }
                ],
            "options": {"by_code": True, "delete_scope_fields_list": ["employee_id"], "dry_run": False}
        }
        res = self.client.post(self.get_url('Employment-batch-update-or-create'), data, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        wd.refresh_from_db()
        self.assertFalse(wd.employment)

    @mock.patch.object(transaction, 'on_commit', lambda t: t())
    def test_clean_wdays_after_employment_recreated_from_deleted(self):
        """When `Employment` is recreated from deleted (as `AbstractActiveModel`), `clean_wdays` must be called to reattach `Employment` to `WorkerDay`"""
        self.network.clean_wdays_on_employment_dt_change = True
        self.network.save()
        self.employment1.delete()
        wd = WorkerDayFactory(
            employment = None,
            employee = self.employment1.employee,
            dt = self.dt_now,
            type_id=WorkerDay.TYPE_WORKDAY
        )
        self.assertFalse(wd.employment)
        self.employment1.dttm_deleted = None
        self.employment1.save()
        wd.refresh_from_db()
        self.assertTrue(wd.employment)

    @mock.patch.object(transaction, 'on_commit', lambda t: t())
    def test_fix_work_types_after_employment_change(self):
        """Tests src.timetable.worker_day.services.fix.FixWdaysService.fix_work_types"""
        self.employment2.employee.user.network.clean_wdays_on_employment_dt_change = True
        self.employment2.employee.user.network.save()
        wd = WorkerDay.objects.create(
            dt=date.today(),
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY
        )
        wd.work_types.set((WorkTypeFactory(shop=self.shop),)) # random WorkType

        # create low and high priority types, link it to Employment
        work_type_low = WorkTypeFactory(shop=self.shop, priority=1, work_type_name=WorkTypeNameFactory(name='low'))
        EmploymentWorkTypeFactory(employment=self.employment2, work_type=work_type_low)
        work_type_high = WorkTypeFactory(shop=self.shop, priority=2, work_type_name=WorkTypeNameFactory(name='high'))
        EmploymentWorkTypeFactory(employment=self.employment2, work_type=work_type_high)
        self.assertEqual(self.employment2.work_types.count(), 2)

        # trigger Employment changes
        self.employment2.dt_hired -= timedelta(1)
        self.employment2.save()

        # work_types were pulled from Employment
        wd.refresh_from_db()
        self.assertTrue(wd.work_types.filter(id=work_type_high.id).exists())
        self.assertFalse(wd.work_types.filter(id=work_type_low.id).exists())

        # Should be idempotent
        self.employment2.dt_hired -= timedelta(1)
        self.employment2.save()

        wd.refresh_from_db()
        self.assertTrue(wd.work_types.filter(id=work_type_high.id).exists())
        self.assertFalse(wd.work_types.filter(id=work_type_low.id).exists())

    @override_settings(TIME_ZONE='UTC')
    def test_employment_is_active_shop_aware(self):
        """Employment.is_active should be aware of shops timezone."""
        today = timezone.now().date()
        self.employment1.dt_hired = today
        self.employment1.dt_fired = None

        dttm = datetime.combine(today, time()) - timedelta(hours=1)  # yesterday 23:00
        with mock.patch.object(timezone, 'now', lambda: dttm):
            # yesterday in UTC, not employed
            self.employment1.shop.timezone = pytz.timezone('UTC')
            self.assertFalse(self.employment1.is_active())

            # today in another timezone, already employed
            self.employment1.shop.timezone = pytz.timezone('Europe/Moscow') # GMT +3
            self.assertTrue(self.employment1.is_active())
