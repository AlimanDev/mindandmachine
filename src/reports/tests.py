from dateutil.relativedelta import relativedelta
from rest_framework.test import APITestCase
from src.util.test import create_departments_and_users
from datetime import date, timedelta
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
