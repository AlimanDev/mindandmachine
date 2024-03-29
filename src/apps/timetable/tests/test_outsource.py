from datetime import datetime, date, timedelta, time

from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status

from src.apps.base.models import Shop, NetworkConnect, Network, User, Employee, Employment, Group, FunctionGroup
from src.apps.events.models import EventType
from src.apps.notifications.models.event_notification import EventEmailNotification
from src.apps.recognition.models import Tick
from src.apps.timetable.events import VACANCY_CONFIRMED_TYPE
from src.apps.timetable.models import ShopMonthStat, TimesheetItem
from src.apps.timetable.models import (
    WorkerDay,
    WorkType,
    WorkTypeName,
    GroupWorkerDayPermission,
    WorkerDayPermission,
    AttendanceRecords,
)
from src.apps.timetable.tests.factories import WorkerDayFactory
from src.interfaces.api.serializers.worker_day import CopyApprovedSerializer
from src.common.mixins.tests import TestsHelperMixin
from src.common.time import DateTimeHelper


class TestOutsource(TestsHelperMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.set_wd_allowed_additional_types()
        cls.client_network = Network.objects.create(
            name='Клиент',
            breaks=cls.breaks,
        )
        cls.client_network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'I': 'подразделение',
                    'R': 'подразделения',
                    'P': 'подразделении',
                }
            }
        )
        cls.client_network.save()
        cls.outsource_network = cls.network
        cls.outsource_network2 = Network.objects.create(
            name='Аутсорс'
        )
        cls.outsource_root_shop = Shop.objects.create(
            name='Outsource',
            region=cls.region,
            network=cls.outsource_network2,
        )
        cls.client_root_shop = Shop.objects.create(
            name='Клиент',
            region=cls.region,
            network=cls.client_network,
        )
        cls.client_shop = Shop.objects.create(
            name='Магазин',
            region=cls.region,
            network=cls.client_network,
            parent=cls.client_root_shop,
            code='client',
        )
        cls.client_admin_group = Group.objects.create(name='Администратор client', code='client admin', network=cls.client_network)
        cls.client_admin_group.subordinates.add(cls.client_admin_group)
        cls.outsource_admin_group = Group.objects.create(name='Администратор outsource', code='outsource admin', network=cls.outsource_network2)
        FunctionGroup.objects.bulk_create([
            FunctionGroup(
                group=g,
                method=method,
                func=func,
                level_up=1,
                level_down=99,
            ) 
            for g in [cls.client_admin_group, cls.outsource_admin_group]
            for func, _ in FunctionGroup.FUNCS_TUPLE 
            for method, _ in FunctionGroup.METHODS_TUPLE
        ])
        GroupWorkerDayPermission.objects.bulk_create(
            GroupWorkerDayPermission(
                group=g,
                worker_day_permission=wdp,
                employee_type=GroupWorkerDayPermission.OTHER_SHOP_OR_NETWORK_EMPLOYEE
            ) 
            for g in [cls.client_admin_group, cls.outsource_admin_group]
            for wdp in WorkerDayPermission.objects.all()
        )
        cls.outsource_user = User.objects.create(
            first_name='outsource',
            last_name='outsource',
            username='outsource',
            network=cls.outsource_network2,
        )
        cls.outsource_employee = Employee.objects.create(
            user=cls.outsource_user,
            tabel_code='outsource',
        )
        cls.outsource_employment = Employment.objects.create(
            employee=cls.outsource_employee,
            shop=cls.outsource_root_shop,
            function_group=cls.outsource_admin_group,
        )
        cls.client_user = User.objects.create(
            first_name='client',
            last_name='client',
            username='client',
            network=cls.client_network,
        )
        cls.client_employee = Employee.objects.create(
            user=cls.client_user,
            tabel_code='client',
        )
        cls.client_employment = Employment.objects.create(
            employee=cls.client_employee,
            shop=cls.client_root_shop,
            function_group=cls.client_admin_group,
        )
        cls.client_work_type_name = WorkTypeName.objects.create(
            network=cls.client_network,
            name='Client work type',
        )
        cls.client_work_type = WorkType.objects.create(
            work_type_name=cls.client_work_type_name,
            shop=cls.client_shop,
        )
        
        cls.network_connect = NetworkConnect.objects.create(client=cls.client_network, outsourcing=cls.outsource_network)
        cls.network_connect2 = NetworkConnect.objects.create(client=cls.client_network, outsourcing=cls.outsource_network2)
        cls.dt_now = date.today()
        ShopMonthStat.objects.create(shop=cls.client_shop, is_approved=True, dt=cls.dt_now.replace(day=1), dttm_status_change=datetime.now())

    def setUp(self):
        self.client.force_authenticate(user=self.client_user)

    def _create_vacancy(self, dt, dttm_work_start, dttm_work_end, is_vacancy=True, is_outsource=True, outsources=[]):
        return self.client.post(
            '/rest_api/worker_day/',
            data={
                'shop_id': self.client_shop.id,
                'is_vacancy': is_vacancy,
                'is_outsource': is_outsource,
                'type': WorkerDay.TYPE_WORKDAY,
                'worker_day_details': [
                    {
                        'work_part': 1.0,
                        'work_type_id': self.client_work_type.id,
                    },
                ],
                'outsources_ids': outsources,
                'dttm_work_start': dttm_work_start,
                'dttm_work_end': dttm_work_end,
                'dt': dt,
                'is_fact': False,
            },
            format='json'
        )
    
    def _create_and_apply_vacancy(self, night_shift=False):
        dt_now = self.dt_now
        dttm_work_start = datetime.combine(dt_now, time(20)) if night_shift else datetime.combine(dt_now, time(8))
        dttm_work_end = datetime.combine(dt_now + timedelta(1), time(8)) if night_shift else datetime.combine(dt_now, time(20))
        vacancy = self._create_vacancy(dt_now, dttm_work_start, dttm_work_end, outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy/')
        self.assertEqual(response.status_code, 200)
        return vacancy

    def test_vacancy_creation(self):
        dt_now = self.dt_now
        not_created = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_vacancy=False)
        self.assertEqual(not_created.json(), {'non_field_errors': ['Только вакансия может быть аутсорс.']})
        not_created = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)))
        self.assertEqual(not_created.json(), {'non_field_errors': ['Не переданы аутсорс сети, которые могут откликнуться на аутсорс вакансию.']})
        created = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,])
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['outsources'][0]['id'], self.network.id)
        WorkerDay.objects.all().delete()
        NetworkConnect.objects.all().delete()
        not_created = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,])
        self.assertEqual(not_created.json(), {'non_field_errors': ['Не переданы аутсорс сети, которые могут откликнуться на аутсорс вакансию.']})

    def test_create_vacancy_with_shop_from_other_network(self):
        NetworkConnect.objects.filter(id=self.network_connect.id).delete()
        dt_now = self.dt_now
        self.client.force_authenticate(user=self.user1)
        not_created = self._create_vacancy(
            dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False)
        self.assertEqual(not_created.json(),
                         {'detail': 'У вас нет прав на создание типа дня "Рабочий день" в подразделении Магазин (Вакансии)'})

    def test_can_create_vacancy_with_shop_from_other_network_but_from_outsource_client(self):
        dt_now = self.dt_now
        self.client.force_authenticate(user=self.user1)
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.CREATE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.SUBORDINATE_EMPLOYEE,
            shop_type=GroupWorkerDayPermission.CLIENT_NETWORK_SHOPS,
        )
        resp = self._create_vacancy(
            dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False)
        self.assertEqual(resp.status_code, 201)

    def test_vacancy_creation_with_null_or_empty_outsourcings_ids(self):
        dt_now = self.dt_now
        created = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False)
        self.assertEqual(created.status_code, 201)
        created = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False, outsources=None)
        self.assertEqual(created.status_code, 201)

    def test_vacancy_get(self):
        dt_now = self.dt_now
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,])
        self._create_vacancy(dt_now + timedelta(1), datetime.combine(dt_now + timedelta(1), time(16)), datetime.combine(dt_now + timedelta(1), time(20)), outsources=[self.outsource_network.id,])
        self._create_vacancy(dt_now + timedelta(1), datetime.combine(dt_now + timedelta(1), time(10)), datetime.combine(dt_now + timedelta(1), time(20)), outsources=[self.outsource_network.id,])
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id])
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network2.id,])
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False)
        self._create_vacancy(dt_now + timedelta(1), datetime.combine(dt_now + timedelta(1), time(16)), datetime.combine(dt_now + timedelta(1), time(20)), is_outsource=False)
        self._create_vacancy(dt_now + timedelta(1), datetime.combine(dt_now + timedelta(1), time(10)), datetime.combine(dt_now + timedelta(1), time(20)), is_outsource=False)
        WorkerDay.objects.all().update(is_approved=True)
        WorkerDay.objects.create(
            employee=self.client_employee,
            employment=self.client_employment,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt_now,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.client_employee,
            employment=self.client_employment,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=dt_now + timedelta(1),
            is_approved=True,
            dttm_work_start=datetime.combine(dt_now + timedelta(1), time(10)),
            dttm_work_end=datetime.combine(dt_now + timedelta(1), time(15)),
            shop=self.client_shop,
            is_vacancy=True,
        )
        WorkerDay.objects.create(
            employee=self.employee1,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=dt_now + timedelta(1),
            is_approved=True,
            dttm_work_start=datetime.combine(dt_now + timedelta(1), time(10)),
            dttm_work_end=datetime.combine(dt_now + timedelta(1), time(15)),
            shop=self.client_shop,
            is_vacancy=True,
        )
        self.client_network.allow_workers_confirm_outsource_vacancy = True
        self.client_network.save()
        response = self.client.get('/rest_api/worker_day/vacancy/?only_available=True&limit=10&offset=0')
        self.assertEqual(response.json()['count'], 6)
        self.client_network.allow_workers_confirm_outsource_vacancy = False
        self.client_network.save()
        response = self.client.get('/rest_api/worker_day/vacancy/?only_available=True&limit=10&offset=0')
        self.assertEqual(response.json()['count'], 2)
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/rest_api/worker_day/vacancy/?only_available=True&limit=10&offset=0')
        self.assertEqual(response.json()['count'], 3)
        resp_data = sorted(response.json()['results'], key=lambda i: i['id'])
        self.assertEqual(len(resp_data[0]['outsources']), 1)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(response.json()['count'], 4)
        self.client.force_authenticate(user=self.client_user)
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id])
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(response.json()['count'], 4)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_confirm_vacancy(self):
        event, _ = EventType.objects.get_or_create(
            code=VACANCY_CONFIRMED_TYPE,
            network=self.client_network,
        )
        subject = 'Сотрудник откликнулся на вакансию.'
        event_notification = EventEmailNotification.objects.create(
            event_type=event,
            subject=subject,
            system_email_template='notifications/email/vacancy_confirmed.html',
        )
        self.client_user.email = 'test@mail.mm'
        self.client_user.save()
        event_notification.users.add(self.client_user)
        dt_now = self.dt_now
        vacancy_without_outsource = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False).json()
        vacancy_without_outsources = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network2.id,]).json()
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f'/rest_api/worker_day/{vacancy_without_outsource["id"]}/confirm_vacancy/')
        self.assertEqual(response.json(), {'result': 'Вы не можете выйти на эту смену, так как данная вакансия находится в другой сети и не подразумевает возможность аутсорсинга.'})
        response = self.client.post(f'/rest_api/worker_day/{vacancy_without_outsources["id"]}/confirm_vacancy/')
        self.assertEqual(response.json(), {'result': 'Вы не можете выйти на эту вакансию так как данная вакансия находится в другой сети и вашей сети не разрешено откликаться на данную вакансию.'})
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy/')
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, subject)
        self.assertEqual(mail.outbox[0].to[0], self.client_user.email)
        self.assertEqual(
            mail.outbox[0].body, 
            f'Здравствуйте, {self.client_user.first_name}!\n\n\n\n\n\n\nАутсорс сотрудник {self.user1.last_name} {self.user1.first_name} откликнулся на вакансию с типом работ {self.client_work_type_name.name}\n'
            f'Дата: {vacancy["dt"]}\nПодразделение: {self.client_shop.name}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        vacancy = WorkerDay.objects.get(id=vacancy['id'])
        self.assertEqual(vacancy.employee_id, self.employee1.id)
        self.assertEqual(vacancy.employment_id, self.employment1.id)
        not_approved_vacancy = WorkerDay.objects.filter(parent_worker_day_id=vacancy.id).first()
        self.assertIsNotNone(not_approved_vacancy)
        self.assertEqual(list(not_approved_vacancy.outsources.all()), [self.outsource_network,])
        self.assertEqual(list(vacancy.outsources.all()), [self.outsource_network,])

    def test_confirm_vacancy_to_worker(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user1.id,
                'employee_id': self.employee1.id,
            }
        )
        self.assertEqual(response.json(), {'non_field_errors': ['В вашей сети нет такого пользователя.']})
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        vacancy = WorkerDay.objects.get(id=vacancy['id'])
        self.assertEqual(vacancy.employee_id, self.employee2.id)
        self.assertEqual(vacancy.employment_id, self.employment2.id)
    
    def test_confirm_vacancy_to_worker_group_perms(self):
        dt_now = self.dt_now
        self.admin_group.subordinates.clear()
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        resp = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {'detail': f'Сотрудник {self.user2.fio} не является Вашим подчиненным.'}
        )
        self.admin_group.subordinates.add(self.employment2.function_group)
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop2)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {'detail': f'Сотрудник {self.user2.fio} не является Вашим подчиненным.'}
        )
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})


    def test_reconfirm_vacancy_to_worker(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        vacancy = WorkerDay.objects.get(id=vacancy['id'])
        self.assertEqual(vacancy.employee_id, self.employee2.id)
        self.assertEqual(vacancy.employment_id, self.employment2.id)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/reconfirm_vacancy_to_worker/',
            data={
                'user_id': self.user3.id,
                'employee_id': self.employee3.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employee_id, self.employee3.id)
        self.assertEqual(vacancy.employment_id, self.employment3.id)
        self.assertIsNone(WorkerDay.objects.filter(employee_id=self.employee2.id, is_vacancy=True).first())
        WorkerDayFactory(
            dt=dt_now,
            is_fact=True,
            is_approved=True,
            employee_id=self.employee3.id,
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/reconfirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вы не можете переназначить сотрудника на данную вакансию, так как сотрудник уже вышел на данную вакансию.'})
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employee_id, self.employee3.id)
        self.assertEqual(vacancy.employment_id, self.employment3.id)
    
    def test_reconfirm_vacancy_to_worker_group_perms(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user3.id,
                'employee_id': self.employee3.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        self.admin_group.subordinates.clear()
        resp = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/reconfirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {'detail': f'Сотрудник {self.user2.fio} не является Вашим подчиненным.'}
        )
        self.admin_group.subordinates.add(self.employment2.function_group)
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop2)
        resp = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/reconfirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(resp.status_code, 403)
        self.assertDictEqual(
            resp.json(),
            {'detail': f'Сотрудник {self.user2.fio} не является Вашим подчиненным.'}
        )
        Employment.objects.filter(employee=self.employee1).update(shop=self.shop)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy["id"]}/reconfirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})

    def test_confirm_outsource_vacancy_from_client_network(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        WorkerDay.objects.create(
            dt=dt_now,
            type_id=WorkerDay.TYPE_HOLIDAY,
            employee=self.client_employee,
            employment=self.client_employment,
            is_approved=True,
        )
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy/')
        self.assertEqual(response.json(), {'result': 'Вы не можете откликнуться на данную вакансию, так как в вашей сети запрещено откликаться на аутсорс вакансии вашей сети.'})
        self.client_network.allow_workers_confirm_outsource_vacancy = True
        self.client_network.save()
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy/')
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})

    def test_get_vacancy_with_worker(self):
        vacancy = self._create_and_apply_vacancy()
        response = self.client.get('/rest_api/worker_day/')
        self.assertEqual(len(response.json()), 2)
        # получаем список отделов с клиентами
        response = self.client.get('/rest_api/department/?include_clients=true')
        self.assertEqual(len(list(filter(lambda x: x['id'] == self.client_shop.id, response.json()))), 1)
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(response.json()['count'], 2)
        response_data = sorted(response.json()['results'], key=lambda i: i['id'])
        data = {
            'id': vacancy['id'],
            'employee_id': self.employee1.id,
            'is_outsource': True,
        }
        response = response_data[0]
        assert_response = {
            'id': response['id'],
            'employee_id': response['employee_id'],
            'is_outsource': response['is_outsource'],
        }
        self.assertEqual(assert_response, data)
        # получаем список отделов с аутсорс организациями
        response = self.client.get('/rest_api/department/?include_outsources=true')
        self.assertEqual(len(list(filter(lambda x: x['id'] == self.root_shop.id, response.json()))), 1)

    def test_get_worker_days_for_urv(self):
        vacancy = self._create_and_apply_vacancy(night_shift=True)
        self.client.logout()
        self._authorize_tick_point(shop=self.client_shop)
        response = self.client.get(self.get_url('TimeAttendanceWorkerDay-list'))
        data = [
            {
                'user_id': self.user1.id, 
                'employees': [
                    {
                        'id': self.employee1.id, 
                        'tabel_code': None, 
                        'shop': {
                            'name': self.employment1.shop.name,
                            'id': self.employment1.shop.id,
                            'timezone': 'Europe/Moscow',
                        },
                        'worker_days': [
                            {
                                'id': vacancy['id'], 
                                'dttm_work_start': vacancy['dttm_work_start'], 
                                'dttm_work_end': vacancy['dttm_work_end']
                            }
                        ],
                        'position': '',
                    }
                ], 
                'first_name': self.user1.first_name, 
                'last_name': self.user1.last_name, 
                'avatar': None,
                'network': {
                    'id': self.user1.network_id, 
                    'name': self.user1.network.name, 
                    'logo': None, 
                    'url': None, 
                    'primary_color': '', 
                    'secondary_color': '', 
                    'allowed_geo_distance_km': None,
                    'allow_creation_several_wdays_for_one_employee_for_one_date': False,
                    'allow_to_manually_set_is_vacancy': False,
                    'enable_camera_ticks': False,
                    'show_worker_day_additional_info': False,
                    'show_restrict_editing_shifts_button': False,
                    'allowed_interval_for_late_arrival': '00:00:00',
                    'allowed_interval_for_early_departure': '00:00:00',
                    'biometry_in_tick_report': False,
                    'default_stats': {
                        'timesheet_employee_top': 'fact_total_all_hours_sum',
                        'timesheet_employee_bottom': 'sawh_hours',
                        'employee_bottom': 'norm_hours_curr_month',
                        'employee_top': 'work_hours_total', 
                        'day_top': 'covering', 
                        'day_bottom': 'deadtime'
                    }, 
                    'show_tabel_graph': True, 
                    'show_worker_day_tasks': False,
                    'show_user_biometrics_block': False,
                    'show_checkbox_for_inspection_version': True,
                    'use_internal_exchange': True,
                    'unaccounted_overtime_threshold': 60,
                    'forbid_edit_employments_came_through_integration': True,
                    'forbid_edit_work_days_came_through_integration': False,
                    'get_position_from_work_type_name_in_calc_timesheet': False,
                    'trust_tick_request': False,
                    'show_cost_for_inner_vacancies': False,
                    'rebuild_timetable_min_delta': 2,
                    'show_remaking_choice': False,
                    'analytics_iframe': '',
                    'analytics_type': 'metabase',
                    'show_employee_shift_schedule_tab': False,
                    'display_chart_in_other_stores': False,
                    'shop_name_form': {
                        "singular": {
                            "I": "магазин",
                            "R": "магазина",
                            "D": "магазину",
                            "V": "магазин",
                            "T": "магазином",
                            "P": "магазине"
                        },
                        "plural": {
                            "I": "магазины",
                            "R": "магазинов",
                            "D": "магазинам",
                            "V": "магазины",
                            "T": "магазинами",
                            "P": "магазинах"
                        }
                    }
                }
            }
        ]
        self.assertEqual(response.json(), data)

    def test_tick_vacancy(self):
        self.network.trust_tick_request = True
        self.network.save()
        vacancy = self._create_and_apply_vacancy()
        resp_coming = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.client_shop.code, 'employee_id': self.employee1.id}),
            content_type='application/json',
        )
        self.assertEqual(resp_coming.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        resp_leaving = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'shop_code': self.client_shop.code, 'employee_id': self.employee1.id}),
            content_type='application/json',
        )
        self.assertEqual(resp_leaving.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)

    def test_attendance_records_vacancy(self):
        vacancy = self._create_and_apply_vacancy()
        att = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt_now, time(7, 45)),
            shop=self.client_shop,
            user=self.user1,
        )
        self.assertEqual(att.type, AttendanceRecords.TYPE_COMING)
        self.assertEqual(att.employee_id, self.employee1.id)
        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt_now, time(7, 45)))
        att = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt_now, time(19, 45)),
            shop=self.client_shop,
            user=self.user1,
        )
        self.assertEqual(att.type, AttendanceRecords.TYPE_LEAVING)
        self.assertEqual(att.employee_id, self.employee1.id)
        wd.refresh_from_db()
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt_now, time(19, 45)))
        self.assertNotEqual(wd.work_hours, timedelta(0))

    def test_cant_approve_vacancy_from_other_network(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f"/rest_api/worker_day/{vacancy['id']}/approve_vacancy/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), ['Вы не можете подтвердить вакансию из другой сети.'])

    def test_approve_vacancy_with_worker_copy_outsources(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        wd = WorkerDay.objects.get(id=vacancy['id'])
        wd.employee = self.employee1
        wd.employment = self.employment1
        wd.save()
        response = self.client.post(f"/rest_api/worker_day/{vacancy['id']}/approve_vacancy/")
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_approved)
        nawd = WorkerDay.objects.filter(parent_worker_day=wd).first()
        self.assertIsNotNone(nawd)
        self.assertEqual(list(nawd.outsources.all()), [self.outsource_network,])

    def test_client_can_get_and_approve_wd_for_employee_from_other_network_emploeed_in_own_shop(self):
        self.employment2.shop = self.client_shop
        self.employment2.save()
        wd = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            type_id='H',
            dt=date.today(),
        )
        response = self.client.get(f'/rest_api/worker_day/?employee_id__in={self.employee2.id}')
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(len(list(filter(lambda x: x['id'] == wd.id, response.json()))), 1)
        response = self.client.post('/rest_api/worker_day/approve/', {
            'shop_id': self.client_shop.id,
            'dt_from': date.today(),
            'dt_to': date.today(),
        })
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_approved)

    def test_outource_do_not_see_vacancies_applied_by_worker_from_other_network(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(len(response.json()['results']), 1)
        self.assertEqual(len(list(filter(lambda x: x["id"] == vacancy["id"], response.json()['results']))), 1)
        self.client.force_authenticate(user=self.outsource_user)
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy/')
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(len(response.json()['results']), 0)

    def test_outource_cant_reconfirm_vacancy_applied_by_worker_from_other_network(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id]).json()
        WorkerDay.objects.all().update(is_approved=True)
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(len(response.json()['results']), 1)
        self.assertEqual(len(list(filter(lambda x: x["id"] == vacancy["id"], response.json()['results']))), 1)
        self.client.force_authenticate(user=self.outsource_user)
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/confirm_vacancy/')
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(f'/rest_api/worker_day/{vacancy["id"]}/reconfirm_vacancy_to_worker/', {'user_id': self.user1.id, 'employee_id': self.employee1.id,})
        self.assertEqual(response.status_code, 403)

    def test_approve_with_worker_copy_outsources(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        wd = WorkerDay.objects.get(id=vacancy['id'])
        wd.employee = self.employee1
        wd.employment = self.employment1
        wd.save()
        response = self.client.post(f"/rest_api/worker_day/approve/", {"shop_id": vacancy['shop_id'], "dt_from": dt_now, "dt_to": dt_now})
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_approved)
        nawd = WorkerDay.objects.filter(parent_worker_day=wd).first()
        self.assertIsNotNone(nawd)
        self.assertEqual(list(nawd.outsources.all()), [self.outsource_network,])

    def test_copy_plan_to_plan_copy_outsources(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        wd = WorkerDay.objects.get(id=vacancy['id'])
        wd.employee = self.employee1
        wd.employment = self.employment1
        wd.save()
        response = self.client.post(
            f"/rest_api/worker_day/copy_approved/", 
            self.dump_data({"employee_ids": [self.employee1.id,], "dates": [dt_now,], "type": CopyApprovedSerializer.TYPE_PLAN_TO_PLAN}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        copied = WorkerDay.objects.filter(parent_worker_day=wd).first()
        self.assertIsNotNone(copied)
        self.assertEqual(list(copied.outsources.all()), [self.outsource_network,])

    def test_copy_plan_to_fact_copy_outsources(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        WorkerDay.objects.all().update(is_approved=True)
        wd = WorkerDay.objects.get(id=vacancy['id'])
        wd.employee = self.employee1
        wd.employment = self.employment1
        wd.save()
        response = self.client.post(
            f"/rest_api/worker_day/copy_approved/", 
            self.dump_data({"employee_ids": [self.employee1.id,], "dates": [dt_now,], "type": CopyApprovedSerializer.TYPE_PLAN_TO_FACT}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        copied = WorkerDay.objects.filter(parent_worker_day=wd).first()
        self.assertIsNotNone(copied)
        self.assertEqual(list(copied.outsources.all()), [])

    def test_copy_range_copy_outsources(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        wd = WorkerDay.objects.get(id=vacancy['id'])
        wd.employee = self.employee1
        wd.employment = self.employment1
        wd.save()
        response = self.client.post(
            f"/rest_api/worker_day/copy_range/", 
            self.dump_data({
                "employee_ids": [self.employee1.id,],
                "from_copy_dt_from": dt_now, 
                "from_copy_dt_to": dt_now,
                "to_copy_dt_from": dt_now + timedelta(1),
                "to_copy_dt_to": dt_now + timedelta(1),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        nawd = WorkerDay.objects.filter(dt=dt_now + timedelta(1), employee=self.employee1.id).first()
        self.assertIsNotNone(nawd)
        self.assertEqual(list(nawd.outsources.all()), [self.outsource_network,])

    def test_exhange_copy_outsources(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,]).json()
        wd = WorkerDay.objects.get(id=vacancy['id'])
        wd.employee = self.employee1
        wd.employment = self.employment1
        wd.save()
        WorkerDay.objects.create(
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt_now,
            employee=self.employee2,
            employment=self.employment2,
        )
        response = self.client.post(
            f"/rest_api/worker_day/exchange/", 
            self.dump_data({
                "employee1_id": self.employee1.id,
                "employee2_id": self.employee2.id,
                "dates": [dt_now,],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        employee1_wd = WorkerDay.objects.filter(employee=self.employee1, dt=dt_now).first()
        employee2_wd = WorkerDay.objects.filter(employee=self.employee2, dt=dt_now).first()
        self.assertIsNotNone(employee1_wd)
        self.assertIsNotNone(employee2_wd)
        self.assertEqual(list(employee2_wd.outsources.all()), [self.outsource_network,])

    def test_outsourcing_network_id__in_filter(self):
        dt_now = self.dt_now
        vacancy = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id]).json()
        vacancy2 = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id]).json()
        vacancy3 = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id]).json()
        vacancy4 = self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network2.id]).json()
        WorkerDay.objects.all().update(is_approved=True)
        response = self.client.get('/rest_api/worker_day/vacancy/?limit=10&offset=0')
        self.assertEqual(len(response.json()['results']), 4)
        response = self.client.get(f'/rest_api/worker_day/vacancy/?limit=10&offset=0&outsourcing_network_id__in={self.outsource_network.id}')
        self.assertEqual(len(response.json()['results']), 3)
        vac_ids = list(map(lambda x: x['id'], response.json()['results']))
        self.assertCountEqual(vac_ids, [vacancy['id'], vacancy2['id'], vacancy3['id']])
        response = self.client.get(f'/rest_api/worker_day/vacancy/?limit=10&offset=0&outsourcing_network_id__in={self.outsource_network2.id}')
        self.assertEqual(len(response.json()['results']), 2)
        vac_ids = list(map(lambda x: x['id'], response.json()['results']))
        self.assertCountEqual(vac_ids, [vacancy3['id'], vacancy4['id']])
        response = self.client.get(f'/rest_api/worker_day/vacancy/?limit=10&offset=0&outsourcing_network_id__in={self.outsource_network.id},{self.outsource_network2.id}')
        self.assertEqual(len(response.json()['results']), 4)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_recalc_timesheet_with_outsource(self):
        WorkerDayFactory(
            shop=self.client_shop,
            dt=self.dt_now,
            employee=self.outsource_employee,
            employment=self.outsource_employment,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=True,
            is_fact=True
        )
        total = TimesheetItem.objects.count()
        data = {
            'shop_id': self.client_shop.id,
            'dt_from': self.dt_now.replace(day=1),
            'dt_to': DateTimeHelper.last_day_in_month(self.dt_now),
            'employee_id__in': [self.outsource_employee.id]
        }
        resp = self.client.post(self.get_url('Timesheet-recalc'), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(TimesheetItem.objects.count(), total)
