from src.base.models import FunctionGroup
import pandas as pd
from django.core import mail
from src.reports.tasks import cron_report
from xlrd import open_workbook
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.reports.reports import PIVOT_TABEL
from src.base.tests.factories import EmployeeFactory, EmploymentFactory, GroupFactory, NetworkFactory, ShopFactory, UserFactory
from src.util.mixins.tests import TestsHelperMixin
from dateutil.relativedelta import relativedelta
from rest_framework.test import APITestCase
from src.util.test import create_departments_and_users
from datetime import date, datetime, time, timedelta
from src.reports.models import ReportConfig, ReportType
from django_celery_beat.models import CrontabSchedule



class TestReportConfig(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)

    def _create_config(self, count_of_periods, period, include_today=False):
        return ReportConfig.objects.create(
            name='Test',
            cron=CrontabSchedule.objects.create(),
            count_of_periods=count_of_periods,
            period=period,
            include_today=include_today,
            report_type=ReportType.objects.first(),
        )

    def test_yesterday(self):
        config = self._create_config(1, ReportConfig.ACC_PERIOD_DAY)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)
    
    def test_today(self):
        config = self._create_config(1, ReportConfig.ACC_PERIOD_DAY, include_today=True)
        dates = config.get_dates()
        data = {
            'dt_from': date.today(),
            'dt_to': date.today(),
        }
        self.assertEquals(data, dates)

    def test_5days(self):
        config = self._create_config(5, ReportConfig.ACC_PERIOD_DAY, include_today=True)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(4),
            'dt_to': date.today(),
        }
        self.assertEquals(data, dates)
        config.include_today = False
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(5),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)

    def test_month(self):
        config = self._create_config(1, ReportConfig.ACC_PERIOD_MONTH, include_today=True)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=1),
            'dt_to': date.today(),
        }
        self.assertEquals(data, dates)
        config.include_today = False
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=1, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)
        config.count_of_periods = 3
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=3, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)

    def test_quarter(self):
        config = self._create_config(1, ReportConfig.ACC_PERIOD_QUARTER, include_today=True)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=3),
            'dt_to': date.today(),
        }
        self.assertEquals(data, dates)
        config.include_today = False
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=3, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)
        config.count_of_periods = 3
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=9, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)

    def test_half_year(self):
        config = self._create_config(1, ReportConfig.ACC_PERIOD_HALF_YEAR, include_today=True)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(months=6),
            'dt_to': date.today(),
        }
        self.assertEquals(data, dates)
        config.include_today = False
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(1) - relativedelta(months=6),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)
        config.count_of_periods = 3
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - timedelta(1) - (relativedelta(months=6) * 3),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)

    def test_year(self):
        config = self._create_config(1, ReportConfig.ACC_PERIOD_YEAR, include_today=True)
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(years=1),
            'dt_to': date.today(),
        }
        self.assertEquals(data, dates)
        config.include_today = False
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(years=1, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)
        config.count_of_periods = 3
        config.save()
        dates = config.get_dates()
        data = {
            'dt_from': date.today() - relativedelta(years=3, days=1),
            'dt_to': date.today() - timedelta(1),
        }
        self.assertEquals(data, dates)


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
        
        cls.dt = datetime.now().date() - timedelta(3)
        cls.now = datetime.now() + timedelta(hours=cls.shop.get_tz_offset())
        cls.cron = CrontabSchedule.objects.create()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            cashbox_details__work_type__work_type_name__name='Кассир',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_employee_working_not_according_to_plan_notification_sent(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject = 'Табель'
            report_config = ReportConfig.objects.create(
                report_type=self.report,
                subject=subject,
                email_text='Табель',
                cron=self.cron,
                name='Test',
                count_of_periods=1,
                period=ReportConfig.ACC_PERIOD_MONTH,
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
            data = open_workbook(file_contents=mail.outbox[0].attachments[0][1])
            df = pd.read_excel(data, engine='xlrd')
            self.assertEquals(len(df.columns), 8)
            self.assertEquals(len(df.values), 3)
            self.assertEquals(list(df.iloc[0, 5:].values), [0.00, 10.75, 10.75])
            self.assertEquals(list(df.iloc[1, 5:].values), [10.75, 10.75, 21.50])
            self.assertEquals(list(df.iloc[2, 5:].values), [10.75, 21.50, 32.25])

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
        
        cls.dt = datetime.now().date()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=cls.shop,
            employment=cls.employment_dir,
            employee=cls.employee_dir,
            dt=cls.dt,
            type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            cashbox_details__work_type__work_type_name__name='Кассир',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user_dir)

    def test_employee_working_not_according_to_plan_notification_sent(self):
        response = self.client.get(f'/rest_api/report/pivot_tabel/?dt_from={self.dt - timedelta(1)}&dt_to={self.dt}')
        self.assertEquals(response.status_code, 200)
        data = open_workbook(file_contents=response.content)
        df = pd.read_excel(data, engine='xlrd')
        self.assertEquals(len(df.columns), 8)
        self.assertEquals(len(df.values), 3)
        self.assertEquals(list(df.iloc[0, 5:].values), [0.00, 10.75, 10.75])
        self.assertEquals(list(df.iloc[1, 5:].values), [10.75, 10.75, 21.50])
        self.assertEquals(list(df.iloc[2, 5:].values), [10.75, 21.50, 32.25])
