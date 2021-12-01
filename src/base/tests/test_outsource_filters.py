from datetime import datetime, date, timedelta, time

from django.test import override_settings
from rest_framework.test import APITestCase

from src.base.models import Shop, NetworkConnect, Network, User, Employee, Employment, Group, FunctionGroup, \
    WorkerPosition
from src.timetable.models import (
    WorkerDay,
    WorkType,
    WorkTypeName,
    GroupWorkerDayPermission,
    WorkerDayPermission,
)
from src.timetable.timesheet.tasks import calc_timesheets
from src.util.mixins.tests import TestsHelperMixin


@override_settings(OUTSOURCE=True)
class TestOutsource(TestsHelperMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.client_network = Network.objects.create(
            name='Клиент',
            breaks=cls.breaks,
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
            code='client',
        )
        cls.cleint_admin_group = Group.objects.create(name='Администратор client', code='client admin', network=cls.client_network)
        FunctionGroup.objects.bulk_create([
            FunctionGroup(
                group=cls.cleint_admin_group,
                method=method,
                func=func,
                level_up=1,
                level_down=99,
            ) for func, _ in FunctionGroup.FUNCS_TUPLE for method, _ in FunctionGroup.METHODS_TUPLE
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
        cls.client_position = WorkerPosition.objects.create(
            name='Client position',
            network=cls.client_network,
        )
        cls.outsource_position = WorkerPosition.objects.create(
            name='Outsource position',
            network=cls.outsource_network,
        )
        
        cls.network_connect = NetworkConnect.objects.create(client=cls.client_network, outsourcing=cls.outsource_network, allow_assign_employements_from_outsource=True, allow_choose_shop_from_client_for_employement=True)
        cls.network_connect2 = NetworkConnect.objects.create(client=cls.client_network, outsourcing=cls.outsource_network2, allow_assign_employements_from_outsource=True, allow_choose_shop_from_client_for_employement=True)
        cls.dt_now = date.today()

    def setUp(self):
        self.client.force_authenticate(user=self.client_user)

    def test_client_can_add_employee_from_outsource_network_to_own_shop(self):
        employees = self.client.get('/rest_api/employee/')
        self.assertEquals(len(employees.json()), 9)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.employee2.id, employees.json()))), 1)

        create_employment_response = self.client.post(
            '/rest_api/employment/', 
            {
                'shop_id': self.client_shop.id,
                'employee_id': self.employee2.id,
                'position_id': self.client_position.id,
                'dt_hired': date.today(),
            }
        )
        self.assertEquals(create_employment_response.status_code, 201)
        self.assertTrue(Employment.objects.filter(shop_id=self.client_shop.id, employee_id=self.employee2.id, position_id=self.client_position.id).exists())
        employments = self.client.get('/rest_api/employment/')
        self.assertEquals(len(list(filter(lambda x: x['id'] == create_employment_response.json()['id'], employments.json()))), 1)

    def test_outsource_can_add_employee_to_shop_from_client_network(self):
        self.client.force_authenticate(user=self.user1)
        employees = self.client.get('/rest_api/employee/')
        self.assertEquals(len(employees.json()), 8)
        shops = self.client.get('/rest_api/department/?include_possible_clients=true')
        self.assertEquals(len(shops.json()), 8)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.client_shop.id, shops.json()))), 1)
        positions = self.client.get('/rest_api/worker_position/')
        self.assertEquals(len(positions.json()), 1)
        positions = self.client.get('/rest_api/worker_position/?include_clients=true')
        self.assertEquals(len(positions.json()), 2)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.client_position.id, positions.json()))), 1)

        create_employment_response = self.client.post(
            '/rest_api/employment/', 
            {
                'shop_id': self.client_shop.id,
                'employee_id': self.employee2.id,
                'position_id': self.client_position.id,
                'dt_hired': date.today(),
            }
        )
        self.assertEquals(create_employment_response.status_code, 201)
        self.assertTrue(Employment.objects.filter(shop_id=self.client_shop.id, employee_id=self.employee2.id, position_id=self.client_position.id).exists())
        employments = self.client.get('/rest_api/employment/')
        self.assertEquals(len(list(filter(lambda x: x['id'] == create_employment_response.json()['id'], employments.json()))), 1)

    def test_outsource_cant_add_employee_to_shop_from_client_network(self):
        self.client.force_authenticate(user=self.user1)
        employees = self.client.get('/rest_api/employee/')
        self.assertEquals(len(employees.json()), 8)
        shops = self.client.get('/rest_api/department/?include_possible_clients=true')
        self.assertEquals(len(shops.json()), 8)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.client_shop.id, shops.json()))), 1)
        position = WorkerPosition.objects.create(
            name='Outsource',
            network=self.outsource_network,
        )

        create_employment_response = self.client.post(
            '/rest_api/employment/', 
            {
                'shop_id': self.client_shop.id,
                'employee_id': self.employee2.id,
                'position_id': position.id,
                'dt_hired': date.today(),
            }
        )
        self.assertEquals(create_employment_response.status_code, 400)
        self.assertEquals(create_employment_response.json(),  {'non_field_errors': ['Сети магазина и должности должны совпадать.']})
        self.network_connect.allow_choose_shop_from_client_for_employement = False
        self.network_connect.save()
        create_employment_response = self.client.post(
            '/rest_api/employment/', 
            {
                'shop_id': self.client_shop.id,
                'employee_id': self.employee2.id,
                'position_id': self.client_position.id,
                'dt_hired': date.today(),
            }
        )
        self.assertEquals(create_employment_response.status_code, 400)
        self.assertEquals(create_employment_response.json(),  {'non_field_errors': ['Вы не можете выбирать магазины из другой сети.']})
        positions = self.client.get('/rest_api/worker_position/?include_clients=true')
        self.assertEquals(len(positions.json()), 2)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.client_position.id, positions.json()))), 0)
        shops = self.client.get('/rest_api/department/?include_possible_clients=true')
        self.assertEquals(len(shops.json()), 6)
        self.network_connect.allow_choose_shop_from_client_for_employement = True
        self.network_connect.save()

    def test_client_does_not_see_employees_from_outsource_network(self):
        self.network_connect.allow_assign_employements_from_outsource = False
        self.network_connect.save()
        employees = self.client.get('/rest_api/employee/')
        self.assertEquals(len(employees.json()), 1)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.employee2.id, employees.json()))), 0)
        self.network_connect.allow_assign_employements_from_outsource = True
        self.network_connect.save()

    def test_client_can_create_worker_day_to_employee_from_other_network_in_own_shop(self):
        Employment.objects.filter(employee=self.employee2.id).update(dt_fired=date.today() - timedelta(1))

        create_employment_response = self.client.post(
            '/rest_api/employment/', 
            {
                'shop_id': self.client_shop.id,
                'employee_id': self.employee2.id,
                'position_id': self.client_position.id,
                'dt_hired': date.today(),
            }
        )
        self.assertEquals(create_employment_response.status_code, 201)
        self.assertTrue(Employment.objects.filter(shop_id=self.client_shop.id, employee_id=self.employee2.id, position_id=self.client_position.id).exists())
        self.assertTrue(Employment.objects.get_active(employee_id=self.employee2.id).count(), 1)
        created_wd = self.client.post(
            '/rest_api/worker_day/',
            {
                'employee_id': self.employee2.id,
                'type': 'H',
                'dt': date.today() + timedelta(1),
            }
        )
        self.assertEquals(created_wd.status_code, 201)

    def test_client_can_get_outsource_positions(self):
        positions = self.client.get('/rest_api/worker_position/?include_outsources=true')
        self.assertEquals(len(positions.json()), 2)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.outsource_position.id, positions.json()))), 1)

    
    def test_filter_get_employee_with_employments_by_shop_network(self):
        Employment.objects.create(
            shop=self.client_shop,
            employee=self.employee1,
        )
        employees = self.client.get('/rest_api/employee/?include_employments=true&show_constraints=true')
        self.assertEquals(len(employees.json()), 9)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.employee1.id, employees.json()))), 1)
        employee = list(filter(lambda x: x['id'] == self.employee1.id, employees.json()))[0]
        self.assertEquals(len(employee['employments']), 2)
        employees = self.client.get(f'/rest_api/employee/?include_employments=true&show_constraints=true&shop_network__in={self.client_network.id}')
        self.assertEquals(len(employees.json()), 9)
        self.assertEquals(len(list(filter(lambda x: x['id'] == self.employee1.id, employees.json()))), 1)
        employee = list(filter(lambda x: x['id'] == self.employee1.id, employees.json()))[0]
        self.assertEquals(len(employee['employments']), 1)


    def test_can_duplicate_worker_day_of_outsource_employee_for_employee_in_own_shop(self):
        empl = Employment.objects.create(
            shop=self.client_shop,
            employee=self.employee1,
        )
        dt = date.today()
        WorkerDay.objects.create(
            employment=empl,
            employee=self.employee1,
            shop=self.client_shop,
            dt=dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
        )
        duplicate = self.client.post(
            '/rest_api/worker_day/duplicate/',
            {
                'from_employee_id': self.employee1.id,
                'to_employee_id': self.client_employee.id,
                'from_dates': [str(dt)],
                'to_dates': [str(dt)],
                'is_approved': False,
            }
        )
        self.assertEquals(duplicate.status_code, 200)
        self.assertTrue(WorkerDay.objects.filter(employee=self.client_employee, dt=dt, is_approved=False, type_id=WorkerDay.TYPE_HOLIDAY).exists())

    def test_get_timesheet_for_outsource_worker(self):
        empl = Employment.objects.create(
            shop=self.client_shop,
            employee=self.employee1,
        )
        dt = date.today()
        if dt.day >= 28:
            dt = (dt + timedelta(5)).replace(day=1)
        WorkerDay.objects.create(
            employment=empl,
            employee=self.employee1,
            shop=self.client_shop,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            is_approved=True,
        )
        with override_settings(FISCAL_SHEET_DIVIDER_ALIAS='nahodka'):
            calc_timesheets(employee_id__in=[self.employee1.id], dt_from=dt, dt_to=dt+timedelta(1), reraise_exc=True)
        response = self.client.get('/rest_api/timesheet/')
        self.assertEquals(len(response.json()), 2)
        self.network_connect.allow_assign_employements_from_outsource = False
        self.network_connect.allow_choose_shop_from_client_for_employement = False
        self.network_connect.save()
        response = self.client.get('/rest_api/timesheet/')
        self.assertEquals(len(response.json()), 0)

    def test_client_can_get_outsource_user(self):
        response = self.client.get(f'/rest_api/user/?id={self.user1.id}')
        self.assertEquals(len(response.json()), 1)
        self.network_connect.allow_assign_employements_from_outsource = False
        self.network_connect.allow_choose_shop_from_client_for_employement = False
        self.network_connect.save()
        response = self.client.get(f'/rest_api/user/?id={self.user1.id}')
        self.assertEquals(len(response.json()), 0)
