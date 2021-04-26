import uuid
from calendar import monthrange
from datetime import datetime, timedelta

from django.test import TestCase
from django.db.models import Q

from src.base.models import Employment, Employee
from src.timetable.models import WorkTypeName, WorkType, WorkerDay
from src.util.dg.tabel import T13TabelDataGetter, MtsTabelDataGetter
from src.util.mixins.tests import TestsHelperMixin


class TestGenerateTabel(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dttm_now = datetime.now()
        cls.dt_now = cls.dttm_now.date()
        for e in Employment.objects.all():
            e.tabel_code = f'A000{e.id}'
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
            tabel_code='A00001234',
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
            tabel_code='A00001234',
        )
        g = MtsTabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        second_data = g.get_data()
        self.assertEqual(len(data['plan_and_fact_hours']), len(second_data['plan_and_fact_hours']))


    def test_generate_custom_t13_tabel(self):
        g = T13TabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 6)
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
                    self.assertIsNone(
                        WorkerDay.objects.filter(
                            Q(is_fact=True) | Q(type=WorkerDay.TYPE_HOLIDAY),
                            Q(employee=employee),
                            dt=dt, 
                            is_approved=True,
                        ).first()
                    )
                    continue
                type = WorkerDay.TYPE_WORKDAY if values['code'] == 'Я' else WorkerDay.TYPE_HOLIDAY
                fact_filter = {}
                if type == WorkerDay.TYPE_WORKDAY:
                    fact_filter['is_fact'] = True
                wd = WorkerDay.objects.filter(dt=dt, type=type, employee=employee, is_approved=True, **fact_filter).first()
                self.assertIsNotNone(wd)
                if wd.type == WorkerDay.TYPE_WORKDAY:
                    self.assertEqual(wd.rounded_work_hours, values['value'])
                    if wd.dt.day <= 15:
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.rounded_work_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.rounded_work_hours
                else:
                    self.assertEqual(values['value'], '')
            self.assertEqual(user['first_half_month_wdays'], first_half_month_wdays)
            self.assertEqual(user['first_half_month_whours'], first_half_month_whours)
            self.assertEqual(user['second_half_month_wdays'], second_half_month_wdays)
            self.assertEqual(user['second_half_month_whours'], second_half_month_whours)

        self.assertEqual(data['users'][2]['fio'], data['users'][3]['fio'])
        self.assertNotEqual(data['users'][2]['tabel_code'], data['users'][3]['tabel_code'])


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
            tabel_code='A00001234',
        )
        g = T13TabelDataGetter(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        data = g.get_data()
        self.assertEqual(len(data['users']), 6)
