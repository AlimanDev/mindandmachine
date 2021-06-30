import uuid
from datetime import timedelta, date, datetime, time
from unittest import mock

from django.db import transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from src.base.models import WorkerPosition, Employment, Break
from src.celery.tasks import delete_inactive_employment_groups
from src.timetable.models import WorkTypeName, EmploymentWorkType, WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter


class TestEmploymentAPI(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.worker_position = WorkerPosition.objects.create(
            name='Директор магазина',
            code='director',
            network=cls.network,
        )
        cls.wt_name = WorkTypeName.objects.create(name='test_name', code='test_code')
        cls.wt_name2 = WorkTypeName.objects.create(name='test_name2', code='test_code2')
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
        }

        resp = self.client.post(
            self.get_url('Employment-list'), data=self.dump_data(data), content_type='application/json')
        return resp

    def test_work_types_added_on_employment_creation(self):
        resp = self._create_employment()
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        for wtn in [self.wt_name, self.wt_name2]:
            self.assertTrue(EmploymentWorkType.objects.filter(
                employment_id=resp_data['id'],
                work_type__work_type_name=wtn,
            ).exists())

    def test_work_types_updated_on_position_change(self):
        another_worker_position = WorkerPosition.objects.create(
            name='Заместитель директора магазина',
            network=self.network,
        )
        another_wt_name = WorkTypeName.objects.create(name='test_another_name', code='test_another_code')
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

        employment_id = self._create_employment().json()['id']

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

    def test_auto_timetable(self):
        employment_ids = list(Employment.objects.filter(shop=self.shop).values_list('id', flat=True))
        employment_ids = employment_ids[1:-2]

        self.assertEqual(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=True).count(), 4)
        data = {
            "employment_ids": employment_ids,
            "auto_timetable": False,
        }
        response = self.client.post('/rest_api/employment/auto_timetable/', data=self.dump_data(data),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=False).count(), 2)
        self.assertEqual(list(
            Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=False).values_list('id',
                                                                                                          flat=True)),
            employment_ids)

    def test_work_hours_change_on_update_position(self):
        dt = date.today()
        break1 = Break.objects.create(
            name='break1',
            network=self.network,
            value='[[0, 1440, [30, 30]]]',
        )
        break2 = Break.objects.create(
            name='break2',
            network=self.network,
            value='[[0, 1440, [30]]]',
        )
        self.worker_position.breaks = break1
        self.worker_position.save()
        another_worker_position = WorkerPosition.objects.create(
            name='Заместитель директора магазина',
            network=self.network,
            breaks=break2,
        )
        resp = self._create_employment().json()
        for i in range(3):
            WorkerDay.objects.create(
                employment_id=resp['id'],
                employee=self.employee2,
                type=WorkerDay.TYPE_WORKDAY,
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
            )
        self.assertEqual(WorkerDay.objects.get(employment_id=resp['id'], dt=dt).work_hours, timedelta(hours=9))
        self.assertEqual(WorkerDay.objects.get(employment_id=resp['id'], dt=dt + timedelta(1)).work_hours,
                         timedelta(hours=9))
        emp = Employment.objects.get(pk=resp['id'])
        emp.position = another_worker_position
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

    def test_empls_cleaned_in_wdays_without_active_employment(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            dt = datetime.now().date()
            self.employment2.employee.user.network.clean_wdays_on_employment_dt_change = True
            self.employment2.employee.user.network.save()

            wd1 = WorkerDay.objects.create(
                shop=self.shop,
                employee=self.employee2,
                employment=self.employment2,
                dt=dt + timedelta(days=50),
                is_fact=False,
                type=WorkerDay.TYPE_WORKDAY,
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
                type=WorkerDay.TYPE_WORKDAY,
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
                type=WorkerDay.TYPE_HOLIDAY,
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
        self.assertEqual(resp.json(), {'detail': 'У вас нет прав для выполнения этой операции.'})

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
            'is_visible': False,
            'function_group_id': self.employee_group.id,
        }
        self.assertEqual(response.json(), data)
        self.employment3.refresh_from_db()
        self.assertIsNone(self.employment3.position_id)
        self.assertIsNone(self.employment3.dt_fired)

    def test_descrease_employment_dt_hired_if_setting_is_enabled(self):
        self.user1.network.descrease_employment_dt_fired_in_api = True
        self.user1.network.save()

        put_data = {
            'position_id': self.worker_position.id,
            'dt_hired': date(2021, 1, 1).strftime('%Y-%m-%d'),
            'dt_fired': date(2021, 5, 25).strftime('%Y-%m-%d'),
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
        ).count() == 0)
        self.assertTrue(Employment.objects.filter(
            shop_id=put_data['shop_id'],
            dt_hired=put_data['dt_hired'],
            dt_fired=date(2021, 5, 24).strftime('%Y-%m-%d'),
            employee_id=put_data['employee_id'],
            position_id=put_data['position_id'],
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

        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
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
                    type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_WORKDAY,
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
