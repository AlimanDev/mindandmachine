import uuid
from calendar import monthrange
from datetime import datetime, timedelta, time

from django.test import override_settings
from django.test import TestCase

from src.base.models import Employment, Employee, NetworkConnect
from src.base.tests.factories import NetworkFactory, ShopFactory, UserFactory, EmployeeFactory, EmploymentFactory
from src.timetable.models import PlanAndFactHours, Timesheet, WorkTypeName, WorkType, WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.timetable.timesheet.tasks import calc_timesheets
from src.util.dg.tabel import T13TabelDataGetter, MtsTabelDataGetter
from src.util.mixins.tests import TestsHelperMixin

@override_settings(FISCAL_SHEET_DIVIDER_ALIAS='nahodka')
class TestGenerateTabel(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.create_departments_and_users()
        cls.dttm_now = datetime.now()
        cls.dt_now = cls.dttm_now.date()
        for e in Employment.objects.all():
            e.save()
        for e in Employee.objects.all():
            e.tabel_code = f'A000{e.id}'
            e.save()
        cls.seconds_employee = Employee.objects.create(
            tabel_code='A00001234',
            user=cls.user2,
        )
        cls.dt_from = cls.dt_now.replace(day=1)
        cls.second_empl = Employment.objects.create(
            code=f'{cls.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            employee=cls.seconds_employee,
            shop=cls.shop,
            function_group=cls.employee_group,
            dt_hired=cls.dt_from,
            salary=100,
        )
        _weekday, days_in_month = monthrange(cls.dt_now.year, cls.dt_now.month)
        cls.dt_to = cls.dt_now.replace(day=days_in_month)
        cls.work_type_name = WorkTypeName.objects.create(name='Консультант')
        cls.work_type_name2 = WorkTypeName.objects.create(name='Кассир')
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(
            work_type_name=cls.work_type_name2,
            shop=cls.shop)
        cls._generate_plan_and_fact_worker_days_for_shop_employments(
            shop=cls.shop, work_type=cls.work_type, dt_from=cls.dt_from, dt_to=cls.dt_to)
        cls.network.okpo = '44412749'
        cls.outsource_network = NetworkFactory(name='Аутсорс сеть', code='outsource')
        cls.outsource_shop = ShopFactory(network=cls.outsource_network)
        cls.outsource_user = UserFactory(network=cls.outsource_network)
        cls.outsource_employee = EmployeeFactory(user=cls.outsource_user)
        cls.outsource_employment = EmploymentFactory(
            employee=cls.outsource_employee,
            shop=cls.outsource_shop,
            dt_hired=cls.dt_from - timedelta(days=90),
            dt_fired=cls.dt_from + timedelta(days=90),
        )
        NetworkConnect.objects.create(
            client=cls.network,
            outsourcing=cls.outsource_network,
        )
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=cls.dt_now,
            employee=cls.outsource_employee,
            shop=cls.shop,
            employment=cls.outsource_employment,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt_now, time(8, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt_now, time(19, 30, 0)),
            cashbox_details__work_type=cls.work_type,
        )
        WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=cls.dt_now,
            employee=cls.outsource_employee,
            shop=cls.shop,
            employment=cls.outsource_employment,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt_now, time(7, 58, 0)),
            dttm_work_end=datetime.combine(cls.dt_now, time(19, 59, 1)),
            cashbox_details__work_type=cls.work_type,
        )
        calc_timesheets()
        cls.types_mapping = {
            'В': WorkerDay.TYPE_HOLIDAY,
            'Я': WorkerDay.TYPE_WORKDAY,
            'Н': WorkerDay.TYPE_ABSENSE,
        }

    def setUp(self) -> None:
        self.outsource_network.refresh_from_db()
        self.second_empl.refresh_from_db()
        self.outsource_employment.refresh_from_db()

    def test_generate_mts_tabel(self):
        g = MtsTabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        for pfh in data['plan_and_fact_hours']:
            dt = pfh.dt
            shop_code = pfh.shop_code
            tabel_code = pfh.tabel_code
            fact_h = pfh.fact_work_hours
            plan_h = pfh.plan_work_hours
            wdays = WorkerDay.objects.filter(
                shop__code=shop_code,
                dt=dt,
                employee__tabel_code=tabel_code,
                is_approved=True,
            )
            fact = wdays.filter(is_fact=True).first()
            plan = wdays.filter(is_fact=False).first()
            if fact_h == 0.0:
                self.assertIsNone(fact)
            else:
                self.assertIsNotNone(fact)
                self.assertEqual(fact.work_hours, timedelta(seconds=fact_h * 3600))
            if plan_h == 0.0:
                self.assertIsNone(plan)
            else:
                self.assertIsNotNone(plan)
                self.assertEqual(plan.work_hours, timedelta(seconds=plan_h * 3600))
        self.second_empl.dt_fired = self.dt_from + timedelta(1)
        self.second_empl.save()
        Employment.objects.create(
            code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            employee=self.seconds_employee,
            shop=self.shop,
            function_group=self.employee_group,
            dt_hired=self.dt_from + timedelta(2),
            salary=100,
        )
        g = MtsTabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        second_data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), len(second_data['plan_and_fact_hours']))

    def test_generate_mts_tabel_for_outsource_shop(self):
        g = MtsTabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = MtsTabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), 1)

    def test_generate_custom_t13_tabel_main(self):
        g = T13TabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, type='M')
        data = g.get_data()
        self.assertEqual(len(data['users']), 7)
        for user in data['users']:
            dt_first = self.dt_from - timedelta(1)
            tabel_code = user['tabel_code']
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0
            employee = Employee.objects.get(tabel_code=tabel_code)
            for day_code, values in user['days'].items():
                dt = dt_first + timedelta(int(day_code.replace('d', '')))
                if dt > self.dt_to:
                    continue
                if values['code'] == '':
                    ts = Timesheet.objects.filter(
                        employee=employee,
                        dt=dt, 
                    ).first()
                    assert_value = ''
                    if employee.id == self.outsource_employee.id:
                        assert_value = ts.main_timesheet_type
                    self.assertEqual(
                        ts.main_timesheet_type,
                        assert_value,
                    )
                    continue
                type = self.types_mapping[values['code']]
                wd = Timesheet.objects.filter(dt=dt, main_timesheet_type=type, employee=employee).first()
                self.assertIsNotNone(wd)
                if wd.main_timesheet_type == WorkerDay.TYPE_WORKDAY:
                    self.assertEqual(wd.main_timesheet_total_hours, values['value'])
                    if wd.dt.day <= 15:
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.main_timesheet_total_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.main_timesheet_total_hours
                else:
                    self.assertEqual(values['value'], '')
            self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
            self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
            self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
            self.assertEqual(user['second_half_month_whours'], second_half_month_whours)
        ind = list(map(lambda x: x['fio'], data['users'])).index(f'{self.user2.last_name} {self.user2.first_name}')
        self.assertEqual(data['users'][ind]['fio'], data['users'][ind + 1]['fio'])
        self.assertNotEqual(data['users'][ind]['tabel_code'], data['users'][ind + 1]['tabel_code'])

    def test_generate_custom_t13_tabel_fact(self):
        g = T13TabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, type='F')
        data = g.get_data()
        self.assertEqual(len(data['users']), 7)
        for user in data['users']:
            dt_first = self.dt_from - timedelta(1)
            tabel_code = user['tabel_code']
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0
            employee = Employee.objects.get(tabel_code=tabel_code)
            for day_code, values in user['days'].items():
                dt = dt_first + timedelta(int(day_code.replace('d', '')))
                if dt > self.dt_to:
                    continue
                if values['code'] == '':
                    ts = Timesheet.objects.filter(
                        employee=employee,
                        dt=dt, 
                    ).first()
                    assert_value = ''
                    if employee.id == self.outsource_employee.id:
                        assert_value = ts.fact_timesheet_type
                    self.assertEqual(
                        ts.fact_timesheet_type,
                        assert_value,
                    )
                    continue
                type = self.types_mapping[values['code']]
                wd = Timesheet.objects.filter(dt=dt, fact_timesheet_type=type, employee=employee).first()
                self.assertIsNotNone(wd)
                if wd.fact_timesheet_type == WorkerDay.TYPE_WORKDAY:
                    self.assertEqual(wd.fact_timesheet_total_hours, values['value'])
                    if wd.dt.day <= 15:
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.fact_timesheet_total_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.fact_timesheet_total_hours
                else:
                    self.assertEqual(values['value'], '')
            self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
            self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
            self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
            self.assertEqual(user['second_half_month_whours'], second_half_month_whours)
        ind = list(map(lambda x: x['fio'], data['users'])).index(f'{self.user2.last_name} {self.user2.first_name}')
        self.assertEqual(data['users'][ind]['fio'], data['users'][ind + 1]['fio'])
        self.assertNotEqual(data['users'][ind]['tabel_code'], data['users'][ind + 1]['tabel_code'])

    def test_generate_custom_t13_tabel_additional(self):
        g = T13TabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, type='A')
        data = g.get_data()
        self.assertEqual(len(data['users']), WorkerDay.objects.filter(shop=self.shop, type=WorkerDay.TYPE_WORKDAY).values('employee').distinct().count())
        for user in data['users']:
            dt_first = self.dt_from - timedelta(1)
            tabel_code = user['tabel_code']
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0
            employee = Employee.objects.get(tabel_code=tabel_code)
            for day_code, values in user['days'].items():
                dt = dt_first + timedelta(int(day_code.replace('d', '')))
                if dt > self.dt_to:
                    continue
                if values['code'] == '':
                    ts = Timesheet.objects.filter(
                        employee=employee,
                        dt=dt,
                        additional_timesheet_hours__gt=0, 
                    ).first()
                    if employee.id == self.outsource_employee.id and ts:
                        continue
                    self.assertIsNone(ts)
                    continue
                wd = Timesheet.objects.filter(dt=dt, additional_timesheet_hours__gt=0, employee=employee).first()
                self.assertIsNotNone(wd)
                self.assertEqual(wd.additional_timesheet_hours, values['value'])
                if wd.dt.day <= 15:
                    first_half_month_wdays += 1
                    first_half_month_whours += wd.additional_timesheet_hours
                else:
                    second_half_month_wdays += 1
                    second_half_month_whours += wd.additional_timesheet_hours
            self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
            self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
            self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
            self.assertEqual(user['second_half_month_whours'], second_half_month_whours)
        ind = list(map(lambda x: x['fio'], data['users'])).index(f'{self.user2.last_name} {self.user2.first_name}')
        self.assertEqual(data['users'][ind]['fio'], data['users'][ind + 1]['fio'])
        self.assertNotEqual(data['users'][ind]['tabel_code'], data['users'][ind + 1]['tabel_code'])

    def test_generate_custom_t13_tabel_for_outsource_shop_main(self):
        g = T13TabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, type='M')
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 0)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = T13TabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, type='M')
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertNotEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 1)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 1)

    def test_generate_custom_t13_tabel_for_outsource_shop_fact(self):
        g = T13TabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, type='F')
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 0)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = T13TabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, type='F')
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertNotEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 1)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 1)

    def test_generate_custom_t13_tabel_for_outsource_shop_additional(self):
        g = T13TabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, type='A')
        data = g.get_data()
        self.assertEqual(len(data['users']), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = T13TabelDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, type='A')
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertNotEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 1)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 1)

    def test_generate_custom_t13_tabel_fired_hired(self):
        self.second_empl.dt_fired = self.dt_from + timedelta(10)
        self.second_empl.save()
        Employment.objects.create(
            code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            employee=self.seconds_employee,
            shop=self.shop,
            function_group=self.employee_group,
            dt_hired=self.dt_from + timedelta(12),
            salary=100,
        )
        g = T13TabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 7)
