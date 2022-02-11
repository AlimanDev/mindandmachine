from calendar import monthrange
from datetime import date, datetime, time, timedelta

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.test import TestCase
from django_celery_beat.models import CrontabSchedule
from rest_framework.test import APITestCase
from src.base.models import FunctionGroup, Network, WorkerPosition
from src.base.tests.factories import EmployeeFactory, EmploymentFactory, GroupFactory, NetworkFactory, ShopFactory, \
    UserFactory
from src.reports.models import ReportConfig, ReportType, Period, UserShopGroups, UserSubordinates
from src.reports.reports import PIVOT_TABEL
from src.reports.tasks import cron_report, fill_user_shop_groups, fill_user_subordinates
from src.timetable.models import ScheduleDeviations, WorkerDay, WorkerDayOutsourceNetwork, WorkerDayType
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.test import create_departments_and_users


class TestReportConfig(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)

    def _create_config(self, count_of_periods, period, period_start=Period.PERIOD_START_YESTERDAY):
        period, _period_created = Period.objects.get_or_create(
            period=period,
            period_start=period_start,
            count_of_periods=count_of_periods,
        )
        return ReportConfig.objects.create(
            name='Test',
            cron=CrontabSchedule.objects.create(),
            report_type=ReportType.objects.first(),
            period=period,
        )

    def test_yesterday(self):
        config = self._create_config(1, Period.ACC_PERIOD_DAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)

    def test_today(self):
        config = self._create_config(1, Period.ACC_PERIOD_DAY, period_start=Period.PERIOD_START_TODAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today(),
            'dt_to': date.today(),
        }
        self.assertEqual(data, dates)

    def test_5days(self):
        config = self._create_config(5, Period.ACC_PERIOD_DAY, period_start=Period.PERIOD_START_TODAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(4),
            'dt_to': date.today(),
        }
        self.assertEqual(data, dates)
        config.period.period_start = Period.PERIOD_START_YESTERDAY
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(5),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)

    def test_month(self):
        config = self._create_config(1, Period.ACC_PERIOD_MONTH, period_start=Period.PERIOD_START_TODAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=1),
            'dt_to': date.today(),
        }
        self.assertEqual(data, dates)
        config.period.period_start = Period.PERIOD_START_YESTERDAY
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': (date.today() - relativedelta(days=1)) - relativedelta(months=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)
        config.period.count_of_periods = 3
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': (date.today() - relativedelta(days=1)) - relativedelta(months=3),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)

    def test_quarter(self):
        config = self._create_config(1, Period.ACC_PERIOD_QUARTER, period_start=Period.PERIOD_START_TODAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=3),
            'dt_to': date.today(),
        }
        self.assertEqual(data, dates)
        config.period.period_start = Period.PERIOD_START_YESTERDAY
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': (date.today() - timedelta(1)) - relativedelta(months=3),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)
        config.period.count_of_periods = 3
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': (date.today() - relativedelta(days=1)) - relativedelta(months=9),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)

    def test_half_year(self):
        config = self._create_config(1, Period.ACC_PERIOD_HALF_YEAR, period_start=Period.PERIOD_START_TODAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=6),
            'dt_to': date.today(),
        }
        self.assertEqual(data, dates)
        config.period.period_start = Period.PERIOD_START_YESTERDAY
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(1) - relativedelta(months=6),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)
        config.period.count_of_periods = 3
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(1) - (relativedelta(months=6) * 3),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)

    def test_year(self):
        config = self._create_config(1, Period.ACC_PERIOD_YEAR, period_start=Period.PERIOD_START_TODAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(years=1),
            'dt_to': date.today(),
        }
        self.assertEqual(data, dates)
        config.period.period_start = Period.PERIOD_START_YESTERDAY
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(years=1, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)
        config.period.count_of_periods = 3
        config.period.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(years=3, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEqual(data, dates)

    def test_period_start(self):
        config = self._create_config(1, Period.ACC_PERIOD_YEAR, period_start=Period.PERIOD_START_PREVIOUS_MONTH)
        self.assertEqual(config.period._get_start_date(date(2021, 1, 23)), date(2020, 12, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 3, 30)), date(2021, 2, 28))
        self.assertEqual(config.period._get_start_date(date(2021, 12, 31)), date(2021, 11, 30))
        config.period.period_start = Period.PERIOD_START_PREVIOUS_QUARTER
        config.period.save()
        self.assertEqual(config.period._get_start_date(date(2021, 1, 23)), date(2020, 12, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 3, 30)), date(2020, 12, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 4, 1)), date(2021, 3, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 6, 30)), date(2021, 3, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 7, 8)), date(2021, 6, 30))
        self.assertEqual(config.period._get_start_date(date(2021, 12, 8)), date(2021, 9, 30))
        config.period.period_start = Period.PERIOD_START_PREVIOUS_HALF_YEAR
        config.period.save()
        self.assertEqual(config.period._get_start_date(date(2021, 1, 23)), date(2020, 12, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 6, 30)), date(2020, 12, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 7, 1)), date(2021, 6, 30))
        self.assertEqual(config.period._get_start_date(date(2021, 12, 31)), date(2021, 6, 30))
        config.period.period_start = Period.PERIOD_START_PREVIOUS_YEAR
        config.period.save()
        self.assertEqual(config.period._get_start_date(date(2021, 1, 23)), date(2020, 12, 31))
        self.assertEqual(config.period._get_start_date(date(2021, 8, 30)), date(2020, 12, 31))

    def test_period_start_prev_month_period_month(self):
        config = self._create_config(1, Period.ACC_PERIOD_MONTH, period_start=Period.PERIOD_START_PREVIOUS_MONTH)
        dates = config.get_dates()
        data = {
            'dt_from': (date.today() - relativedelta(months=1)).replace(day=1),
            'dt_to': (date.today() - relativedelta(months=1)) + relativedelta(day=31),
        }
        self.assertEqual(data, dates)


class TestPivotTabelReportNotifications(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
            director=cls.user_dir,
        )
        cls.employee_dir = EmployeeFactory(user=cls.user_dir, tabel_code='dir')
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs, tabel_code='urs')
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        cls.report, _created = ReportType.objects.get_or_create(
            code=PIVOT_TABEL, network=cls.network)

        cls.dt = (datetime.now().date() - relativedelta(months=1)).replace(day=21)
        cls.now = datetime.now() + timedelta(hours=cls.shop.get_tz_offset())
        cls.cron = CrontabSchedule.objects.create()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            cashbox_details__work_type__work_type_name__name='Директор',
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt - timedelta(1),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt - timedelta(1), time(8)),
            dttm_work_end=datetime.combine(cls.dt - timedelta(1), time(20)),
            cashbox_details__work_type__work_type_name__name='Кассир',
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            cashbox_details__work_type__work_type_name__name='Кассир',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_pivot_tabel_report_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Табель'
            period, _period_created = Period.objects.get_or_create(
                count_of_periods=1,
                period=Period.ACC_PERIOD_MONTH,
                period_start=Period.PERIOD_START_PREVIOUS_MONTH,
            )
            report_config = ReportConfig.objects.create(
                report_type=self.report,
                subject=subject,
                email_text='Табель',
                cron=self.cron,
                name='Test',
                period=period,
            )
            report_config.users.add(self.user_dir)
            report_config.users.add(self.user_urs)
            report_config.shops_to_notify.add(self.shop)
            cron_report()
            self.assertEqual(len(mail.outbox), 3)
            self.assertEqual(mail.outbox[0].subject, subject)
            emails = sorted(
                [
                    outbox.to[0]
                    for outbox in mail.outbox
                ]
            )
            self.assertEqual(emails, [self.user_dir.email, self.shop.email, self.user_urs.email])
            df = pd.read_excel(mail.outbox[0].attachments[0][1])
            self.assertEqual(len(df.columns), 6 + monthrange(self.dt.year, self.dt.month)[1])
            self.assertEqual(len(df.values), 3)
            first_date = datetime.combine(self.dt - timedelta(1), time())
            second_date = datetime.combine(self.dt, time())
            self.assertEqual(list(df.loc[0, [first_date, second_date, 'Часов за период']].values), [0.00, 10.75, 10.75])
            self.assertEqual(list(df.loc[1, [first_date, second_date, 'Часов за период']].values), [10.75, 10.75, 21.50])
            self.assertEqual(list(df.loc[2, [first_date, second_date, 'Часов за период']].values), [10.75, 21.50, 32.25])


class TestReportsViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
            director=cls.user_dir,
        )
        cls.employee_dir = EmployeeFactory(user=cls.user_dir, tabel_code='dir')
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs, tabel_code='urs')
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        FunctionGroup.objects.create(
            func='Reports_pivot_tabel',
            group=cls.group_dir,
            access_type='ALL',
        )

        cls.dt = (datetime.now().date() - relativedelta(months=1)).replace(day=21)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            cashbox_details__work_type__work_type_name__name='Директор',
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt - timedelta(1),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt - timedelta(1), time(8)),
            dttm_work_end=datetime.combine(cls.dt - timedelta(1), time(20)),
            cashbox_details__work_type__work_type_name__name='Кассир',
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=cls.dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            cashbox_details__work_type__work_type_name__name='Кассир',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_report_pivot_tabel_get(self):
        response = self.client.get(f'/rest_api/report/pivot_tabel/?dt_from={self.dt - timedelta(1)}&dt_to={self.dt}')
        self.assertEqual(response.status_code, 200)
        df = pd.read_excel(response.content)
        self.assertEqual(len(df.columns), 8)
        self.assertEqual(len(df.values), 3)
        self.assertEqual(list(df.iloc[0, 5:].values), [0.00, 10.75, 10.75])
        self.assertEqual(list(df.iloc[1, 5:].values), [10.75, 10.75, 21.50])
        self.assertEqual(list(df.iloc[2, 5:].values), [10.75, 21.50, 32.25])


class TestScheduleDeviation(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        self.position = WorkerPosition.objects.create(
            name='Должность сотрудника',
            network=self.network,
        )
        self.employment1.position = self.position
        self.employment1.save()
        self.client.force_authenticate(self.user1)

    def assertHours(self, 
        fact_work_hours=.0, 
        plan_work_hours=.0, 
        fact_manual_work_hours=.0, 
        late_arrival_hours=.0, 
        early_departure_hours=.0,
        early_arrival_hours=.0,
        late_departure_hours=.0,
        fact_without_plan_work_hours=.0,
        lost_work_hours=.0,
        late_arrival_count=0,
        early_departure_count=0,
        early_arrival_count=0,
        late_departure_count=0,
        fact_without_plan_count=0,
        lost_work_hours_count=0,
    ):
        data = {
            'fact_work_hours': fact_work_hours, 
            'plan_work_hours': plan_work_hours, 
            'fact_manual_work_hours': fact_manual_work_hours, 
            'late_arrival_hours': late_arrival_hours, 
            'early_departure_hours': early_departure_hours,
            'early_arrival_hours': early_arrival_hours, 
            'late_departure_hours': late_departure_hours, 
            'fact_without_plan_work_hours': fact_without_plan_work_hours, 
            'lost_work_hours': lost_work_hours, 
            'late_arrival_count': late_arrival_count, 
            'early_departure_count': early_departure_count, 
            'early_arrival_count': early_arrival_count, 
            'late_departure_count': late_departure_count, 
            'fact_without_plan_count': fact_without_plan_count, 
            'lost_work_hours_count': lost_work_hours_count,
        }
        self.assertEqual(ScheduleDeviations.objects.values(*data.keys())[0], data)

    def test_plan_and_fact_hours_values(self):
        dt = date.today()
        wd_plan = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            dt=dt,
        )
        self.assertHours(plan_work_hours=10.75, lost_work_hours=10.75, lost_work_hours_count=1)

        wd_fact = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            dt=dt,
            closest_plan_approved=wd_plan,
        )
        
        wd_fact_not_approved = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            dt=dt,
            closest_plan_approved=wd_plan,
        )
        self.assertHours(plan_work_hours=10.75, fact_work_hours=10.75)
        wd_fact.created_by = self.user1
        wd_fact.save()
        self.assertHours(plan_work_hours=10.75, fact_work_hours=10.75, fact_manual_work_hours=10.75)
        wd_fact.dttm_work_start = datetime.combine(dt, time(7))
        wd_fact.dttm_work_end = datetime.combine(dt, time(19))
        wd_fact.created_by = None
        wd_fact.last_edited_by = None
        wd_fact.save()
        self.assertHours(plan_work_hours=10.75, fact_work_hours=10.75, early_arrival_hours=1.0, early_arrival_count=1, early_departure_hours=1.0, early_departure_count=1)
        wd_fact.dttm_work_start = datetime.combine(dt, time(9))
        wd_fact.dttm_work_end = datetime.combine(dt, time(20, 30))
        wd_fact.save()
        self.assertHours(plan_work_hours=10.75, fact_work_hours=10.25, late_arrival_hours=1.0, late_arrival_count=1, late_departure_hours=0.5, late_departure_count=1, lost_work_hours=0.5, lost_work_hours_count=1)
        wd_plan.dttm_work_start = datetime.combine(dt, time(9))
        wd_plan.dttm_work_end = datetime.combine(dt, time(14))
        wd_plan.save()
        wd_fact.dttm_work_start = datetime.combine(dt, time(14))
        wd_fact.dttm_work_end = datetime.combine(dt, time(19))
        wd_fact.closest_plan_approved = None
        wd_fact.save()
        self.assertHours(plan_work_hours=4.5, fact_work_hours=4.5, lost_work_hours=4.5, lost_work_hours_count=1, fact_without_plan_work_hours=4.5, fact_without_plan_count=1)
        wd_fact2 = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(20)),
            dttm_work_end=datetime.combine(dt, time(23)),
            dt=dt,
        )
        self.assertHours(plan_work_hours=4.5, fact_work_hours=7.0, lost_work_hours=4.5, lost_work_hours_count=1, fact_without_plan_work_hours=7.0, fact_without_plan_count=2)

        wd_plan2 = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(15)),
            dttm_work_end=datetime.combine(dt, time(20)),
            dt=dt,
        )
        wd_fact.dttm_work_start = datetime.combine(dt, time(8, 30))
        wd_fact.dttm_work_end = datetime.combine(dt, time(14))
        wd_fact.closest_plan_approved = wd_plan
        wd_fact.save()
        wd_fact2.dttm_work_start = datetime.combine(dt, time(14, 30))
        wd_fact2.dttm_work_end = datetime.combine(dt, time(20, 30))
        wd_fact2.closest_plan_approved = wd_plan2
        wd_fact2.save()
        self.assertHours(plan_work_hours=9.0, fact_work_hours=10.5, early_arrival_hours=1.0, early_arrival_count=2, late_departure_hours=0.5, late_departure_count=1)
        wd_fact.dttm_work_start = datetime.combine(dt, time(9, 30))
        wd_fact.save()
        self.assertHours(plan_work_hours=9.0, fact_work_hours=9.5, early_arrival_hours=0.5, early_arrival_count=1, late_departure_hours=0.5, late_departure_count=1, late_arrival_count=1, late_arrival_hours=0.5, lost_work_hours_count=1, lost_work_hours=0.5)

    def test_get_schedule_deviation(self):
        dt = date.today()
        wd_plan1 = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(14)),
            dt=dt,
        )
        wd_plan2 = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(15)),
            dttm_work_end=datetime.combine(dt, time(20)),
            dt=dt,
        )
        wd_plan3 = WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            is_approved=True,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_fact=False,
            dt=dt + timedelta(1),
        )
        wd_plan4 = WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop2,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(20)),
            dt=dt,
        )
        WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(7, 30)),
            dttm_work_end=datetime.combine(dt, time(14, 30)),
            dt=dt,
            closest_plan_approved=wd_plan1,
        )
        WorkerDayFactory(
            employee=self.employee1,
            employment=self.employment1,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            cashbox_details__work_type__work_type_name__name='Работа',
            dttm_work_start=datetime.combine(dt, time(15, 30)),
            dttm_work_end=datetime.combine(dt, time(20, 30)),
            dt=dt,
            closest_plan_approved=wd_plan2,
            last_edited_by=self.user1,
        )
        vacancy = WorkerDayFactory(
            is_vacancy=True,
            employee=None,
            employment=None,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Грузчик',
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(18)),
            dt=dt,
        )
        outsource_vacancy = WorkerDayFactory(
            is_vacancy=True,
            employee=None,
            employment=None,
            shop=self.shop,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            cashbox_details__work_type__work_type_name__name='Грузчик',
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(18)),
            dt=dt,
        )
        WorkerDayOutsourceNetwork.objects.bulk_create(
            [
                WorkerDayOutsourceNetwork(
                    workerday=outsource_vacancy,
                    network=Network.objects.create(name=name),
                )
                for name in ['Аутсорс сеть 1', 'Аутсорс сеть 2']
            ]
        )
        report = self.client.get(f'/rest_api/report/schedule_deviation/?dt_from={dt}&dt_to={dt+timedelta(1)}&shop_ids={self.shop.id}')
        data = pd.read_excel(report.content).fillna('')
        self.assertEqual(
            list(data.iloc[10, :].values), 
            [1, self.shop.name, datetime.combine(dt, time(0, 0)), f'{self.user1.fio} ', '-', self.root_shop.name, 'штат', self.position.name, 'Биржа смен', 10,
            10.5, 4.5, 0.5, 1, 0.5, 1, 0, 0, 1, 2, 0, 0, 0, 0]
        )
        self.assertEqual(
            list(data.iloc[11, :].values), 
            [2, self.shop2.name, datetime.combine(dt, time(0, 0)), f'{self.user2.fio} ',
            self.employee2.tabel_code, self.shop.name, 'штат', '-', 'Биржа смен', 8.75,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8.75, 1]
        )
        self.assertEqual(
            list(data.iloc[12, :].values), 
            [3, self.shop.name, datetime.combine(dt, time(0, 0)), '-', '-', '-', 'штат', 'Грузчик', 'Биржа смен', 8.75,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8.75, 1]
        )
        self.assertEqual(
            list(data.iloc[13, :].values), 
            [4, self.shop.name, datetime.combine(dt, time(0, 0)), '-', '-', 'Аутсорс сеть 1', 'не штат', 'Грузчик', 'Биржа смен', 8.75,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8.75, 1]
        )

    def test_get_schedule_deviation_no_data(self):
        dt = date.today()
        report = self.client.get(f'/rest_api/report/schedule_deviation/?dt_from={dt}&dt_to={dt+timedelta(1)}')
        self.assertEqual(report.status_code, 200)
        data = pd.read_excel(report.content).fillna('')
        self.assertEqual(len(data), 10)

    def test_get_schedule_deviation_different_worker_day_types(self):
        dt_from = date.today()
        dt_to = dt_from - timedelta(1)
        for w_type in WorkerDayType.objects.all():
            dt_to += timedelta(1)
            kwargs = {
                'shop': None,
            }
            if w_type.is_work_hours:
                kwargs = {
                    'dttm_work_start': datetime.combine(dt_to, time(8)),
                    'dttm_work_end': datetime.combine(dt_to, time(20)),
                    'cashbox_details__work_type__work_type_name__name': 'Работа',
                    'shop': self.shop,
                }

            WorkerDayFactory(
                employee=self.employee1,
                employment=self.employment1,
                is_approved=True,
                type_id=w_type.code,
                is_fact=False,
                dt=dt_to,
                **kwargs,
            )
        
        report = self.client.get(f'/rest_api/report/schedule_deviation/?dt_from={dt_from}&dt_to={dt_to}')
        data = pd.read_excel(report.content).fillna('')
        for i, wd_type in enumerate(WorkerDayType.objects.all()):
            self.assertEqual(
                list(data.iloc[10 + i, [0, 1, 2, 3, 5, 6, 7, 8]].values), 
                [i + 1, self.shop.name if wd_type.is_work_hours else '-', datetime.combine(dt_from + timedelta(i), time(0, 0)), 
                f'{self.user1.fio} ', self.root_shop.name, 'штат', self.position.name, 'Биржа смен' if wd_type.code == WorkerDay.TYPE_WORKDAY else wd_type.name]
            )


class TestFillReportsData(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.base_shop = ShopFactory(code='base', network=cls.network)
        cls.division1 = ShopFactory(parent=cls.base_shop, code='division1', network=cls.network)
        cls.region1 = ShopFactory(parent=cls.division1, code='region1', network=cls.network)
        cls.shop1 = ShopFactory(parent=cls.region1, code='shop1', network=cls.network)
        cls.group_admin = GroupFactory(code='admin', name='Администратор', network=cls.network)
        cls.group_urs = GroupFactory(code='urs', name='УРС', network=cls.network)
        cls.group_director = GroupFactory(code='director', name='Директор', network=cls.network)
        cls.group_worker = GroupFactory(code='worker', name='Сотрудник', network=cls.network)
        cls.group_admin.subordinates.add(cls.group_urs, cls.group_director, cls.group_worker)
        cls.group_urs.subordinates.add(cls.group_director, cls.group_worker)
        cls.group_director.subordinates.add(cls.group_worker)
        cls.position_admin = WorkerPosition.objects.create(group=cls.group_admin, name='Администратор', code='admin', network=cls.network)
        cls.position_director = WorkerPosition.objects.create(group=cls.group_director, name='Директор', code='director', network=cls.network)
        cls.position_urs = WorkerPosition.objects.create(group=cls.group_urs, name='УРС', code='urs', network=cls.network)
        cls.position_seller = WorkerPosition.objects.create(group=cls.group_worker, name='Продавец-кассир', code='seller', network=cls.network)
        cls.dt_now = datetime.now()
        cls.employment_admin = EmploymentFactory(
            employee__user__network=cls.network,
            shop=cls.base_shop, function_group=cls.group_admin,
        )
        cls.employment_urs = EmploymentFactory(
            employee__user__network=cls.network,
            shop=cls.region1, position=cls.position_urs,
        )
        cls.employment_dir = EmploymentFactory(
            employee__user__network=cls.network,
            shop=cls.shop1, position=cls.position_director,
        )
        cls.employment_worker = EmploymentFactory(
            employee__user__network=cls.network,
            shop=cls.shop1, position=cls.position_seller,
        )

    def test_fill_user_shop_groups(self):
        fill_user_shop_groups()
        self.assertEqual(UserShopGroups.objects.filter(user=self.employment_admin.employee.user).count(), 4)
        self.assertEqual(UserShopGroups.objects.filter(user=self.employment_urs.employee.user).count(), 2)
        self.assertEqual(UserShopGroups.objects.filter(user=self.employment_dir.employee.user).count(), 1)
        self.assertEqual(UserShopGroups.objects.filter(user=self.employment_worker.employee.user).count(), 1)

    def test_fill_user_subordinates(self):
        fill_user_subordinates(use_user_shop_groups=True)
        self.assertEqual(UserSubordinates.objects.filter(user=self.employment_admin.employee.user).count(), 3)
        self.assertEqual(UserSubordinates.objects.filter(user=self.employment_urs.employee.user).count(), 2)
        self.assertEqual(UserSubordinates.objects.filter(user=self.employment_dir.employee.user).count(), 1)
        self.assertEqual(UserSubordinates.objects.filter(user=self.employment_worker.employee.user).count(), 0)
