from datetime import timedelta, time, datetime, date

from django.core import mail
from django.test import override_settings
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APITestCase

from src.apps.base.models import (
    Network,
    Employment,
    Shop,
    Employee,
    User,
)
from src.apps.events.models import EventType
from src.apps.notifications.models.event_notification import EventEmailNotification
from src.apps.timetable.events import VACANCY_CONFIRMED_TYPE
from src.apps.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.apps.timetable.tests.factories import WorkerDayFactory
from src.common.mixins.tests import TestsHelperMixin
from src.common.models_converter import Converter


class TestVacancy(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/vacancy/'
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
        cls.dt_now = date.today()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.vacancy = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee1,
            employment=cls.employment1,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
            comment='Test',
        )
        cls.vacancy2 = WorkerDay.objects.create(
            shop=cls.shop,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
            is_approved=True,
            comment='Test',
        )
        cls.vac_wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy2,
            work_part=1,
        )
        cls.wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy,
            work_part=0.5,
        )
        cls.wd_details2 = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy,
            work_part=0.5,
        )
        cls.set_wd_allowed_additional_types()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_vacancy(self):
        data = {
            'id': None,
            'dt': Converter.convert_date(self.dt_now),
            'dttm_work_start': datetime.combine(self.dt_now, time(hour=11, minute=30)),
            'dttm_work_end': datetime.combine(self.dt_now, time(hour=20, minute=30)),
            'is_fact': False,
            'is_vacancy': True,
            'shop_id': self.shop.id,
            'type': "W",
            'worker_day_details': [
                {
                    'work_part': 1,
                    'work_type_id': self.work_type1.id
                },
            ],
            'employee_id': None
        }

        resp = self.client.post(self.get_url('WorkerDay-list'), data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def _test_vacancy_ordering(self, ordering_field, desc):
        if getattr(self.vacancy, ordering_field) == getattr(self.vacancy2, ordering_field):
            return

        ordering = ordering_field
        v1_first = getattr(self.vacancy, ordering_field) < getattr(self.vacancy2, ordering_field)
        if desc:
            ordering = '-' + ordering_field
            v1_first = not v1_first
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100&ordering={ordering}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], (self.vacancy if v1_first else self.vacancy2).id)
        self.assertEqual(resp.json()['results'][-1]['id'], (self.vacancy2 if v1_first else self.vacancy).id)

    def test_vacancy_ordering(self):
        for ordering_field in ['id', 'dt', 'dttm_work_start', 'dttm_work_end']:
            self._test_vacancy_ordering(ordering_field, desc=False)
            self._test_vacancy_ordering(ordering_field, desc=True)

    def test_default_dt_from_and_dt_to_filers(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dt=self.dt_now - timedelta(days=1))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dt=self.dt_now + timedelta(days=35))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 0)

        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dt=self.dt_now + timedelta(days=27))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_default_vacancy_ordering_is_dttm_work_start_asc(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)))
        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=12, minute=30)))

        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], self.vacancy.id)

        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=12, minute=30)))
        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)))

        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], self.vacancy2.id)

    def test_get_list(self):
        WorkerDay.objects.all().delete()
        self.admin_group.subordinates.clear()
        self.admin_group.subordinates.add(self.employee_group)
        self.employment1.shop = self.shop
        self.employment1.save()
        outsource_network = Network.objects.create(name='outsource')
        outsource_user = User.objects.create(
            username='outsource',
            network=outsource_network,
        )
        outsource_shop = Shop.objects.create(
            name='outsource',
            network=outsource_network,
            region=self.region,
        )
        outsource_employee = Employee.objects.create(
            user=outsource_user,
            tabel_code='outsource',
        )
        outsource_employment = Employment.objects.create(
            employee=outsource_employee,
            shop=outsource_shop,
        )
        vacanct_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            is_approved=True,
            comment='Test',
        )
        own_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee1,
            employment=self.employment1,
            is_approved=True,
        )
        outsource_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=outsource_employee,
            employment=outsource_employment,
            is_approved=True,
            is_outsource=True,
        )
        subordinate_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee2,
            employment=self.employment2,
            is_approved=True,
        )
        not_subordinate_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee5,
            employment=self.employment5,
            is_approved=True,
        )
        not_own_shop_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee8,
            employment=self.employment8,
            is_approved=True,
        )
        not_subordinate__in_own_shop_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee6,
            employment=self.employment6,
            is_approved=True,
        )
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 5)
        vacanct_vacancy_resp = list(filter(lambda x: x['id'] == vacanct_vacancy.id, response.json()['results']))
        self.assertEqual(len(vacanct_vacancy_resp), 1)
        self.assertEqual(vacanct_vacancy_resp[0]['comment'], 'Test')
        self.assertCountEqual(
            list(map(lambda x: x['id'], response.json()['results'])),
            [vacanct_vacancy.id, own_vacancy.id, outsource_vacancy.id, subordinate_vacancy.id,
             not_subordinate__in_own_shop_vacancy.id],
        )

    def test_get_list_shift_length(self):
        response = self.client.get(
            f'{self.url}?shop_id={self.shop.id}&shift_length_min=7:00:00&shift_length_max=9:00:00&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_vacant_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_vacant=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_outsource_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 2)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)
        self.vacancy2.is_outsource = True
        self.vacancy2.save()
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=false&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_confirm_vacancy(self):
        event, _ = EventType.objects.get_or_create(
            code=VACANCY_CONFIRMED_TYPE,
            network=self.network,
        )
        subject = 'Сотрудник откликнулся на вакансию.'
        event_notification = EventEmailNotification.objects.create(
            event_type=event,
            subject=subject,
            system_email_template='notifications/email/vacancy_confirmed.html',
        )
        self.user1.email = 'test@mail.mm'
        self.user1.save()
        event_notification.users.add(self.user1)
        self.shop.__class__.objects.filter(id=self.shop.id).update(email=True)
        pnawd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)),
            dttm_work_end=datetime.combine(self.dt_now, time(hour=20, minute=30)),
            dt=self.dt_now,
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type1,
            worker_day=pnawd,
            work_part=1,
        )
        pawd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        self.client.force_authenticate(user=self.user2)
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
        )
        self.add_group_perm(self.employee_group, 'WorkerDay_confirm_vacancy', 'POST')
        response = self.client.post(f'/rest_api/worker_day/{self.vacancy2.id}/confirm_vacancy/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, subject)
        self.assertEqual(mail.outbox[0].to[0], self.user1.email)
        self.assertEqual(
            mail.outbox[0].body,
            f'Здравствуйте, {self.user1.first_name}!\n\n\n\n\n\n\nСотрудник {self.user2.last_name} {self.user2.first_name} откликнулся на вакансию с типом работ {self.work_type1.work_type_name.name}\n'
            f'Дата: {self.vacancy2.dt}\nПодразделение: {self.shop.name}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )

        self.assertFalse(WorkerDay.objects.filter(id=pawd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(is_approved=False, dt=self.vacancy2.dt, employee=self.employee2).exists())

        # можно откликнуться на вакансию,
        # если время не пересекается с другой вакансией на которую уже откликнулся или назначен
        vacancy3 = WorkerDayFactory(
            employee_id=None,
            employment_id=None,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now, time(18)),
            dttm_work_end=datetime.combine(self.dt_now, time(22)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_approved=True,
            cashbox_details__work_type=self.work_type1,
        )
        response = self.client.post(f'/rest_api/worker_day/{vacancy3.id}/confirm_vacancy/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})

        # нельзя откликнуться на вакансию,
        # если время вакансии пересекается с другой/другими днями
        vacancy4 = WorkerDayFactory(
            employee_id=None,
            employment_id=None,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now, time(12)),
            dttm_work_end=datetime.combine(self.dt_now, time(22)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_approved=True,
            cashbox_details__work_type=self.work_type1,
        )
        response = self.client.post(f'/rest_api/worker_day/{vacancy4.id}/confirm_vacancy/')
        self.assertContains(
            response, text='Операция не может быть выполнена. Недопустимое пересечение времени', status_code=400)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_approve_vacancy(self):
        self.shop.network.only_fact_hours_that_in_approved_plan = True
        self.shop.network.save()
        WorkerDay.objects.filter(id=self.vacancy.id).update(employee_id=None, is_approved=False)
        wd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.vacancy.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.vacancy.id, is_approved=True).exists())

        WorkerDay.objects.filter(id=self.vacancy.id).update(employee=wd.employee, is_approved=False)

        wd_fact = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_approved=True,
            is_fact=True,
            created_by=self.user2,
            last_edited_by=self.user2,
        )
        self.assertEqual(wd_fact.work_hours, timedelta(0))
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        wd = WorkerDay.objects.filter(id=self.vacancy.id).first()
        self.assertIsNotNone(wd)
        self.assertTrue(wd.is_approved)
        self.assertTrue(WorkerDay.objects.filter(
            dt=wd.dt,
            employee_id=wd.employee_id,
            is_fact=wd.is_fact,
            is_approved=True,
        ).exists())
        wd_fact.refresh_from_db()
        self.assertEqual(wd_fact.closest_plan_approved_id, wd.id)
        self.assertEqual(wd_fact.work_hours, timedelta(seconds=31500))

    def test_get_only_available(self):
        '''
        Создаем дополнительно 3 вакансии на 3 дня вперед
        Вернется только одна вакансия, так как:
        1. У сотрудника подтвержденный рабочий день
        2. У сотрудника нет подтвержденного плана
        3. Сотрудник уволен до даты вакансии
        '''
        WorkerDay.objects.create(
            employee=self.employment1.employee,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employment1.employee,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(1), time(hour=11, minute=30)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(1), time(hour=20, minute=30)),
            dt=self.dt_now + timedelta(1),
            is_approved=False,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(1), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(1), time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(1),
            is_vacancy=True,
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(2), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(2), time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(2),
            is_vacancy=True,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.employment1.employee,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now + timedelta(3),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(2), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(2), time(17)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(3),
            is_vacancy=True,
            is_approved=True,
        )
        self.employment1.dt_fired = self.dt_now + timedelta(2)
        self.employment1.save()
        resp = self.client.get('/rest_api/worker_day/vacancy/?only_available=true&offset=0&limit=10&is_vacant=true')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['dt'], self.dt_now.strftime('%Y-%m-%d'))

    def test_update_vacancy_type_to_deleted(self):
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop2,
        )
        vacancy = WorkerDay.objects.create(
            shop=self.shop2,
            employee=self.employee2,
            employment=self.employment2,
            dttm_work_start=datetime.combine(self.dt_now, time(9)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            comment='Test',
        )
        response = self.client.put(
            f'/rest_api/worker_day/{vacancy.id}/',
            self.dump_data(
                {
                    "dt": vacancy.dt,
                    "is_fact": False,
                    "type": WorkerDay.TYPE_EMPTY,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertFalse(vacancy.is_vacancy)
        response = self.client.put(
            f'/rest_api/worker_day/{vacancy.id}/',
            self.dump_data(
                {
                    "employee_id": self.employee2.id,
                    "shop_id": self.shop2.id,
                    "dt": vacancy.dt,
                    "dttm_work_start": datetime.combine(vacancy.dt, time(8, 0, 0)),
                    "dttm_work_end": datetime.combine(vacancy.dt, time(20, 0, 0)),
                    "type": WorkerDay.TYPE_WORKDAY,
                    "is_fact": False,
                    "worker_day_details": [
                        {
                            "work_part": 1.0,
                            "work_type_id": self.work_type.id
                        },
                    ]
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertTrue(vacancy.is_vacancy)
    
    def test_cost_per_hour_in_list(self):
        self.vacancy.cost_per_hour = 120120.45
        self.vacancy.save()
        response = self.client.get(f"{self.url}?limit=100")
        vacancy = list(filter(lambda x: x['id'] == self.vacancy.id, response.json()['results']))[0]
        self.assertEqual(vacancy['cost_per_hour'], '120120.45')
        self.assertEqual(vacancy['total_cost'], 1171174.3875)

    def test_refuse_vacancy(self):
        WorkerDay.objects.all().delete()
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=self.dt_now.replace(day=1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
        )
        pawd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(19)),
            is_approved=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        # refuse empty vacancy, no errors
        resp = self.client.post(self.get_url('WorkerDay-refuse-vacancy', pk=vacancy.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'result': 'Вакансия успешно отозвана.'})

        # apply vacancy
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employee_id, self.employee2.id)
        self.assertEqual(vacancy.employment_id, self.employment2.id)
        self.assertIsNotNone(
            WorkerDay.objects.filter(is_approved=False, type=WorkerDay.TYPE_WORKDAY, employee_id=self.employee2.id).first(),
        )
        # refuse vacancy, no errors
        resp = self.client.post(self.get_url('WorkerDay-refuse-vacancy', pk=vacancy.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'result': 'Вакансия успешно отозвана.'})
        vacancy.refresh_from_db()
        self.assertIsNone(vacancy.employee_id)
        self.assertIsNone(vacancy.employment_id)
        self.assertIsNone(
            WorkerDay.objects.filter(is_approved=False, type=WorkerDay.TYPE_WORKDAY, employee_id=self.employee2.id).first(),
        )

    def test_cant_refuse_vacancy_when_fact_exist(self):
        WorkerDay.objects.all().delete()
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=self.dt_now.replace(day=1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
        )
        pawd = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(19)),
            is_approved=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/confirm_vacancy_to_worker/',
            data={
                'user_id': self.user2.id,
                'employee_id': self.employee2.id,
            }
        )
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employee_id, self.employee2.id)
        self.assertEqual(vacancy.employment_id, self.employment2.id)
        self.assertIsNotNone(
            WorkerDay.objects.filter(is_approved=False, type=WorkerDay.TYPE_WORKDAY, employee_id=self.employee2.id).first(),
        )
        AttendanceRecords.objects.create(
            user=self.user2,
            shop=self.shop,
            dttm=datetime.combine(self.dt_now, time(7, 50)),
            dt=self.dt_now,
            type=AttendanceRecords.TYPE_COMING
        )
        resp = self.client.post(self.get_url('WorkerDay-refuse-vacancy', pk=vacancy.id))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {'result': "Вы не можете отозвать вакансию, так как сотрудник уже вышел на данную вакансию."})
    
    def test_can_change_applied_vacancy_with_non_subordinate_user(self):
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop,
        )
        self.employment1.shop = self.shop
        self.employment1.save()
        vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee8,
            employment=self.employment8,
            is_approved=False,
            created_by=self.user1,
        )
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.UPDATE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.MY_NETWORK_EMPLOYEE,
            shop_type=GroupWorkerDayPermission.MY_SHOPS,
        )
        wd_update_data = {
            "type": WorkerDay.TYPE_WORKDAY,
            "employee_id": self.employee8.id,
            "dt": self.dt_now,
            "shop_id": self.shop.id,
            "dttm_work_start": datetime.combine(self.dt_now, time(10)),
            "dttm_work_end": datetime.combine(self.dt_now, time(20)),
            "worker_day_details": [
                {
                    "work_part": 1.0,
                    "work_type_id": self.work_type.id
                },
            ]
        }
        response = self.client.put(
            self.get_url('WorkerDay-detail', pk=vacancy.id), 
            data=self.dump_data(wd_update_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.dttm_work_start, datetime.combine(self.dt_now, time(10)))

        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.DELETE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.MY_NETWORK_EMPLOYEE,
            shop_type=GroupWorkerDayPermission.MY_SHOPS,
        )
        response = self.client.delete(
            self.get_url('WorkerDay-detail', pk=vacancy.id),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WorkerDay.objects.filter(id=vacancy.id).exists())
        WorkerDay.objects.all().delete()
        vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(20)),
            employee=self.employee8,
            employment=self.employment8,
            is_approved=False,
            created_by=self.user1,
        )
        options = {
            'return_response': True,
        }
        data = {
           'data':  [
                {
                    "id": vacancy.id,
                    "shop_id": self.shop.id,
                    "employee_id": self.employee8.id,
                    "dt": self.dt_now,
                    "is_fact": False,
                    "is_approved": False,
                    "type": WorkerDay.TYPE_WORKDAY,
                    "dttm_work_start": datetime.combine(self.dt_now, time(10)),
                    "dttm_work_end": datetime.combine(self.dt_now, time(21)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                },
            ],
            'options': options,
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.dttm_work_start, datetime.combine(self.dt_now, time(10)))
        
        delete_data = {
            'data': [],
            'options': {
                'delete_scope_values_list': [
                    {
                        'employee_id': self.employee8.id,
                        'dt': self.dt_now,
                        'is_fact': False,
                        'is_approved': False,
                    },
                ]
            }
        }
        resp = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'), self.dump_data(delete_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(WorkerDay.objects.filter(id=vacancy.id).exists())

    def test_get_and_create_vacancy_with_shop_name(self):
        response = self.client.get(f"{self.get_url('WorkerDay-vacancy')}?extra_fields=shop__name,shop__code&limit=100&offset=0&is_vacant=true")
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(len(response_data['results']), 1)
        self.assertEqual(response_data['results'][0].get('shop__name'), self.shop.name)
        self.assertFalse('shop__code' in response_data['results'][0])
        self.assertFalse('shop__name' in response_data['results'][0]['worker_day_details'][0])

        create_data = response_data['results'][0]

        create_data['is_approved'] = False
        create_data['extra_fields'] = 'shop__name,shop__code'

        response = self.client.post(self.get_url('WorkerDay-list'), data=self.dump_data(create_data), content_type='application/json')
        response_data = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response_data.get('shop__name'), self.shop.name)
        self.assertFalse('shop__code' in response_data)
        self.assertFalse('shop__name' in response_data['worker_day_details'][0])

    def test_pagination(self):
        for i in range(10):
            WorkerDayFactory(
                shop=self.shop,
                is_approved=True,
                is_vacancy=True,
                dt=self.dt_now,
                dttm_work_start=datetime.combine(self.dt_now, time(10)),
                dttm_work_end=datetime.combine(self.dt_now, time(20)),
                employee=None,
                employment=None,
                type_id=WorkerDay.TYPE_WORKDAY,
            )
        response = self.client.get(f"{self.get_url('WorkerDay-vacancy')}?limit=100&offset=0&is_vacant=true")
        self.assertEqual(response.json()['count'], 11)
        response = self.client.get(f"{self.get_url('WorkerDay-vacancy')}?limit=5&offset=0&is_vacant=true&return_total_count=false")
        self.assertEqual(response.json()['count'], 5)
