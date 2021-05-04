from datetime import datetime, date, timedelta, time
import json

from dateutil.relativedelta import relativedelta
from rest_framework.test import APITestCase

from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkType, WorkTypeName, GroupWorkerDayPermission, WorkerDayPermission
from src.base.models import Shop, NetworkConnect, Network, User, Employee, Employment, Group, FunctionGroup
from src.timetable.models import ShopMonthStat
from src.util.mixins.tests import TestsHelperMixin


class TestOutsource(TestsHelperMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.client_network = Network.objects.create(
            name='Клиент'
        )
        cls.outsource_network = cls.network
        cls.outsource_network2 = Network.objects.create(
            name='Аутсорс'
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
        )
        cls.cleint_admin_group = Group.objects.create(name='Администратор client', code='client admin', network=cls.client_network)
        FunctionGroup.objects.bulk_create([
            FunctionGroup(
                group=cls.cleint_admin_group,
                method=method,
                func=func,
                level_up=1,
                level_down=99,
            ) for func in FunctionGroup.FUNCS for method in FunctionGroup.METHODS
        ])
        GroupWorkerDayPermission.objects.bulk_create(
            GroupWorkerDayPermission(
                group=cls.cleint_admin_group,
                worker_day_permission=wdp,
            ) for wdp in WorkerDayPermission.objects.all()
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
            function_group=cls.cleint_admin_group,
        )
        cls.client_work_type_name = WorkTypeName.objects.create(
            network=cls.client_network,
            name='Client work type',
        )
        cls.client_work_type = WorkType.objects.create(
            work_type_name=cls.client_work_type_name,
            shop=cls.client_shop,
        )
        
        NetworkConnect.objects.create(client=cls.client_network, outsourcing=cls.outsource_network)
        NetworkConnect.objects.create(client=cls.client_network, outsourcing=cls.outsource_network2)
        cls.dt_now = date.today()

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


    def test_vacancy_get(self):
        dt_now = self.dt_now
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id,])
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network.id, self.outsource_network2.id])
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), outsources=[self.outsource_network2.id,])
        self._create_vacancy(dt_now, datetime.combine(dt_now, time(8)), datetime.combine(dt_now, time(20)), is_outsource=False)
        self.client.force_authenticate(user=self.user1)
        WorkerDay.objects.all().update(is_approved=True)
        response = self.client.get('/rest_api/worker_day/vacancy/?only_available=True&limit=10&offset=0')
        self.assertEqual(response.json()['count'], 2)