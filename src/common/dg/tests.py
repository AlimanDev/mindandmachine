import uuid
from calendar import monthrange
from datetime import datetime, timedelta, time
from decimal import Decimal

from django.test import TestCase, override_settings

from src.apps.base.models import Employment, Employee, NetworkConnect
from src.apps.base.tests import NetworkFactory, ShopFactory, UserFactory, EmployeeFactory, EmploymentFactory
from src.apps.timetable.models import TimesheetItem, WorkTypeName, WorkType, WorkerDay, WorkerDayType, EmploymentWorkType
from src.apps.timetable.tests.factories import WorkerDayFactory
from src.apps.timetable.timesheet.tasks import calc_timesheets
from src.common.dg.timesheet import (
    DefaultTimesheetDataGetter, T13TimesheetDataGetter, MtsTimesheetDataGetter, TimesheetLinesDataGetter
)
from src.common.mixins.tests import TestsHelperMixin


class TestGenerateTabel(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(fiscal_sheet_divider_alias='nahodka')
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
        cls.work_type_name = WorkTypeName.objects.create(name='Консультант', network=cls.network)
        cls.work_type_name2 = WorkTypeName.objects.create(name='Кассир', network=cls.network)
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(
            work_type_name=cls.work_type_name2,
            shop=cls.shop)
        cls._generate_plan_and_fact_worker_days_for_shop_employments(
            shop=cls.shop, work_type=cls.work_type, dt_from=cls.dt_from, dt_to=cls.dt_to)
        cls.network.okpo = '44412749'
        cls.outsource_network = NetworkFactory(name='Аутсорс сеть', code='outsource', fiscal_sheet_divider_alias='nahodka')
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
            type_id=WorkerDay.TYPE_WORKDAY,
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
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt_now, time(7, 58, 0)),
            dttm_work_end=datetime.combine(cls.dt_now, time(19, 59, 1)),
            cashbox_details__work_type=cls.work_type,
        )
        calc_timesheets(dt_from=cls.dt_from, dt_to=cls.dt_to)
        cls.types_mapping = dict(WorkerDayType.objects.values_list(
            'excel_load_code',
            'code',
        ))

    def setUp(self) -> None:
        self.outsource_network.refresh_from_db()
        self.second_empl.dt_fired = None
        self.second_empl.save()
        self.outsource_employment.refresh_from_db()

    def test_generate_mts_tabel(self):
        g = MtsTimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
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
        g = MtsTimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        second_data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), len(second_data['plan_and_fact_hours']))

    def test_generate_mts_tabel_for_outsource_shop(self):
        g = MtsTimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = MtsTimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), 1)

    def test_generate_custom_t13_tabel_main(self):
        g = T13TimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_MAIN)
        data = g.get_data()
        # self.assertEqual(len(data['users']), 7)
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
                    ts = TimesheetItem.objects.filter(
                        employee=employee,
                        dt=dt, 
                    ).first()
                    assert_value = ''
                    if employee.id == self.outsource_employee.id:
                        assert_value = ts.day_type_id
                    self.assertEqual(
                        ts.day_type_id,
                        assert_value,
                    )
                    continue
                type_id = self.types_mapping[values['code']]
                wd = TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=dt, day_type_id=type_id, employee=employee).first()
                self.assertIsNotNone(wd)
                if wd.day_type_id == WorkerDay.TYPE_WORKDAY:
                    self.assertEqual(wd.day_hours + wd.night_hours, values['value'])
                    if wd.dt.day <= 15:
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.day_hours + wd.night_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.day_hours + wd.night_hours
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
        g = T13TimesheetDataGetter(
            shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_FACT)
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
                    ts = TimesheetItem.objects.filter(
                        employee=employee,
                        dt=dt, 
                    ).first()
                    assert_value = ''
                    if employee.id == self.outsource_employee.id:
                        assert_value = ts.day_type_id
                    self.assertEqual(
                        ts.day_type_id,
                        assert_value,
                    )
                    continue
                type = self.types_mapping[values['code']]
                wd = TimesheetItem.objects.filter(
                    timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
                    dt=dt, day_type_id=type, employee=employee,
                ).first()
                self.assertIsNotNone(wd)
                if wd.day_type_id == WorkerDay.TYPE_WORKDAY:
                    self.assertEqual(wd.day_hours + wd.night_hours, values['value'])
                    if wd.dt.day <= 15:
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.day_hours + wd.night_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.day_hours + wd.night_hours
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
        g = T13TimesheetDataGetter(
            shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)
        data = g.get_data()
        self.assertEqual(len(data['users']), TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, shop=self.shop, day_hours__gt=0).values('employee').distinct().count())
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
                    ts = TimesheetItem.objects.filter(
                        timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
                        employee=employee,
                        dt=dt,
                        day_hours__gt=0,
                    ).first()
                    if employee.id == self.outsource_employee.id and ts:
                        continue
                    self.assertIsNone(ts)
                    continue
                wd = TimesheetItem.objects.filter(
                    timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
                    dt=dt, day_hours__gt=0, employee=employee,
                ).first()
                self.assertIsNotNone(wd)
                self.assertEqual(wd.day_hours + wd.night_hours, values['value'])
                if wd.dt.day <= 15:
                    first_half_month_wdays += 1
                    first_half_month_whours += wd.day_hours + wd.night_hours
                else:
                    second_half_month_wdays += 1
                    second_half_month_whours += wd.day_hours + wd.night_hours
            self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
            self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
            self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
            self.assertEqual(user['second_half_month_whours'], second_half_month_whours)
        two_empls = list(filter(lambda x: x['fio'] == f'{self.user2.last_name} {self.user2.first_name}', data['users']))
        if len(two_empls) == 2: # не всегда может быть доп табель
            self.assertNotEqual(two_empls[0]['tabel_code'], two_empls[1]['tabel_code'])

    def test_generate_custom_t13_tabel_main_and_additional(self):
        g = T13TimesheetDataGetter(
            shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=[TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, TimesheetItem.TIMESHEET_TYPE_MAIN])
        data = g.get_data()
        for user in data['users']:
            dt_first = self.dt_from - timedelta(1)
            tabel_code = user['tabel_code']
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0
            employee = Employee.objects.get(tabel_code=tabel_code)
            if user["timesheet_type"] == TimesheetItem.TIMESHEET_TYPE_MAIN:
                for day_code, values in user['days'].items():
                    dt = dt_first + timedelta(int(day_code.replace('d', '')))
                    if dt > self.dt_to:
                        continue
                    if values['code'] == '':
                        ts = TimesheetItem.objects.filter(
                            employee=employee,
                            dt=dt,
                        ).first()
                        assert_value = ''
                        if employee.id == self.outsource_employee.id:
                            assert_value = ts.day_type_id
                        self.assertEqual(
                            ts.day_type_id,
                            assert_value,
                        )
                        continue
                    type = self.types_mapping[values['code']]
                    wd = TimesheetItem.objects.filter(
                        timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                        dt=dt, day_type_id=type, employee=employee,
                    ).first()
                    self.assertIsNotNone(wd)
                    if wd.day_type_id == WorkerDay.TYPE_WORKDAY:
                        self.assertEqual(wd.day_hours + wd.night_hours, values['value'])
                        if wd.dt.day <= 15:
                            first_half_month_wdays += 1
                            first_half_month_whours += wd.day_hours + wd.night_hours
                        else:
                            second_half_month_wdays += 1
                            second_half_month_whours += wd.day_hours + wd.night_hours
                    else:
                        self.assertEqual(values['value'], '')
                self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
                self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
                self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
                self.assertEqual(user['second_half_month_whours'], second_half_month_whours)
            elif user["timesheet_type"] == TimesheetItem.TIMESHEET_TYPE_ADDITIONAL:
                for day_code, values in user['days'].items():
                    dt = dt_first + timedelta(int(day_code.replace('d', '')))
                    if dt > self.dt_to:
                        continue
                    if values['code'] == '':
                        ts = TimesheetItem.objects.filter(
                            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
                            employee=employee,
                            dt=dt,
                            day_hours__gt=0,
                        ).first()
                        if employee.id == self.outsource_employee.id and ts:
                            continue
                        self.assertIsNone(ts)
                        continue
                    wd = TimesheetItem.objects.filter(
                        timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
                        dt=dt, day_hours__gt=0, employee=employee,
                    ).first()
                    self.assertIsNotNone(wd)
                    self.assertEqual(wd.day_hours + wd.night_hours, values['value'])
                    if wd.dt.day <= 15:
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.day_hours + wd.night_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.day_hours + wd.night_hours
                self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
                self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
                self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
                self.assertEqual(user['second_half_month_whours'], second_half_month_whours)
        ind = list(map(lambda x: x['fio'], data['users'])).index(f'{self.user2.last_name} {self.user2.first_name}')
        self.assertEqual(data['users'][ind]['fio'], data['users'][ind + 1]['fio'])


    def test_generate_custom_t13_tabel_for_outsource_shop_main(self):
        g = T13TimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_MAIN)
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 0)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = T13TimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_MAIN)
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertNotEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 1)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 1)

    def test_generate_custom_t13_tabel_for_outsource_shop_fact(self):
        g = T13TimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_FACT)
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 0)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = T13TimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_FACT)
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertNotEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 1)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 1)

    def test_generate_custom_t13_tabel_for_outsource_shop_additional(self):
        g = T13TimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)
        data = g.get_data()
        self.assertEqual(len(data['users']), 0)

        self.outsource_network.set_settings_value('tabel_include_other_shops_wdays', True)
        self.outsource_network.save()

        g = T13TimesheetDataGetter(shop=self.outsource_shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)
        data = g.get_data()
        self.assertEqual(len(data['users']), 1)
        user_data = data['users'][0]
        self.assertNotEqual(user_data['full_month_whours'], 0)
        self.assertEqual(user_data['full_month_wdays'], 1)
        self.assertEqual(len(list(filter(lambda x: x['value'] != '', user_data['days'].values()))), 1)


    def test_generate_tabel_with_2_days_on_one_date(self):
        WorkerDay.objects.all().delete()
        dttms = [
            (datetime.combine(self.dt_now, time(8)), datetime.combine(self.dt_now, time(14))),
            (datetime.combine(self.dt_now, time(16)), datetime.combine(self.dt_now, time(20))),
        ]
        self.employee2.refresh_from_db()
        for start, end in dttms:
            approved_wd = None
            for is_fact in [False, True]:
                for is_approved in [False, True]:
                    wd = self._create_worker_day(
                        self.employment2, 
                        start,
                        end,
                        shop_id=self.shop.id,
                        is_fact=is_fact,
                        is_approved=is_approved,
                    )
                    if not is_fact and is_approved:
                        approved_wd = wd
                    elif is_fact:
                        wd.closest_plan_approved = approved_wd
                        wd.save()
        
        calc_timesheets(dt_from=self.dt_from, dt_to=self.dt_to)
        self.assertEqual(TimesheetItem.objects.filter(dt=self.dt_now, employee=self.employee2, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT).count(), 2)

        g = T13TimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to, timesheet_types=TimesheetItem.TIMESHEET_TYPE_FACT)
        data = g.get_data()
        user_data = list(filter(lambda x: x['tabel_code'] == self.employee2.tabel_code, data['users']))[0]
        self.assertEqual(user_data['full_month_wdays'], 1)

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
        g = T13TimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 7)

    def test_timesheet_lines_generator_get_data(self):
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
        g = TimesheetLinesDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 7)

        self.shop.network.set_settings_value('timesheet_include_curr_shop_employees_wdays', False)
        g = TimesheetLinesDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 7)

        self.shop.network.set_settings_value('timesheet_include_curr_shop_wdays', False)
        g = TimesheetLinesDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 0)

        self.shop.network.set_settings_value('timesheet_include_curr_shop_employees_wdays', True)
        g = TimesheetLinesDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 6)

    def test_timesheet_lines_generator_get_data_with_holiday_and_workday_on_one_date(self):
        WorkerDay.objects.all().delete()
        TimesheetItem.objects.all().delete()
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        holiday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_HOLIDAY,
        ).get()
        holiday_type.allowed_additional_types.add(workday_type)
        WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt_now,
            employee=self.employee2,
            shop=self.shop,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt_now,
            employee=self.employee2,
            shop=self.shop,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_HOLIDAY,
        )
        calc_timesheets()
        g = TimesheetLinesDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        d = list(filter(lambda i: i['fio'] == self.employee2.user.fio, data['users']))[0]["days"]
        self.assertDictEqual(d[f'd{self.dt_now.day}'], {'value': Decimal('8.75')})

    def test_generate_tabel_for_many_timesheets_on_one_day(self):
        WorkerDay.objects.all().delete()
        TimesheetItem.objects.all().delete()
        WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt_now,
            employee=self.employee2,
            dttm_work_start=datetime.combine(self.dt_now, time(3)),
            dttm_work_end=datetime.combine(self.dt_now, time(16)),
            shop=self.shop,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt_now,
            employee=self.employee2,
            dttm_work_start=datetime.combine(self.dt_now, time(16)),
            dttm_work_end=datetime.combine(self.dt_now, time(23)),
            shop=self.shop,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            cashbox_details__work_type=self.work_type,
        )
        calc_timesheets()
        g = DefaultTimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        d = list(filter(lambda i: i['fio'] == self.employee2.user.fio, data['users']))[0]["days"]
        self.assertDictEqual(d[f'd{self.dt_now.day}'], {'value': Decimal('17.76')})

    def test_generate_tabel_when_user_has_no_name(self):
        self.user2.first_name = ''
        self.user2.save()
        g = DefaultTimesheetDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        d = list(filter(lambda i: i['fio'] == self.employee2.user.fio, data['users']))
        self.assertNotEqual(len(d), 0)

    def test_group_by_work_type(self):
        WorkerDay.objects.all().delete()
        TimesheetItem.objects.all().delete()
        Employment.objects.exclude(id=self.employment2.id).delete()
        self.shop.network.set_settings_value('move_to_add_timesheet_if_work_type_name_differs', True)
        self.shop.network.save()
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=self.work_type,
            priority=1,
        )
        dt = self.dt_now.replace(day=1)
        WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=dt,
            employee=self.employee2,
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            shop=self.shop,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=dt + timedelta(days=1),
            employee=self.employee2,
            dttm_work_start=datetime.combine(dt + timedelta(days=1), time(8)),
            dttm_work_end=datetime.combine(dt + timedelta(days=1), time(20)),
            shop=self.shop,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            cashbox_details__work_type=self.work_type2,
        )
        calc_timesheets()
        g = TimesheetLinesDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        lines = list(filter(lambda i: i['fio'] == self.employee2.user.fio, data['users']))
        self.assertEqual(len(lines), 2)
        lines.sort(key=lambda i: i['position'])
        self.assertEqual(lines[0]['position'], 'Кассир')
        self.assertEqual(lines[1]['position'], 'Консультант')
