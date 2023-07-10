import json
import os
import tempfile
from datetime import datetime, time, date, timedelta
from unittest import mock
from celery.app.task import Task

from django.test import TestCase, override_settings
from freezegun import freeze_time

from src.apps.base.tests import (
    ShopFactory,
    NetworkFactory,
    EmploymentFactory,
)
from src.apps.exchange.models import SystemExportStrategy, ExportJob, LocalFilesystemConnector
from src.apps.exchange.tasks import run_export_job
from src.apps.forecast.models import (
    OperationTypeName,
    OperationType,
)
from src.apps.reports.models import Period
from src.common.mixins.tests import TestsHelperMixin


class TestExportData(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(
            code='pobeda',
        )
        cls.shop1_code = '22e9b174-8188-11eb-80ba-0050568a6492'
        cls.shop1 = ShopFactory(code=cls.shop1_code)
        cls.shop2_code = '07e6d8fc-87d9-11eb-80bb-0050568a6492'
        cls.shop2 = ShopFactory(code=cls.shop2_code)
        cls.shop3_code = '938e3dcd-6824-11ea-80e8-0050568ab54f'
        cls.shop3 = ShopFactory(code=cls.shop3_code)
        cls.otn_bills_count = OperationTypeName.objects.create(
            network=cls.network,
            name='Количество чеков',
            code='bills_count',
        )
        cls.otn_goods_count = OperationTypeName.objects.create(
            network=cls.network,
            name='Количество товаров',
            code='goods_count',
        )
        cls.shop3_ot_bills_count = OperationType.objects.create(
            operation_type_name=cls.otn_bills_count,
            shop=cls.shop3,
        )
        cls.shop3_ot_goods_count = OperationType.objects.create(
            operation_type_name=cls.otn_goods_count,
            shop=cls.shop3,
        )
        cls.local_fs_connector = LocalFilesystemConnector.objects.create(name='local')

    @freeze_time('2021-09-26')
    def test_export_pivot_table(self):
        employment = EmploymentFactory()
        dt_now = date.today()
        self._create_worker_day(
            employment=employment,
            dttm_work_start=datetime.combine(dt_now, time(10, 00)),
            dttm_work_end=datetime.combine(dt_now, time(20, 00)),
            is_approved=True,
            is_fact=True,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            export_strategy = SystemExportStrategy.objects.create(
                strategy_type=SystemExportStrategy.WORK_HOURS_PIVOT_TABLE,
                period=Period.objects.create(
                    count_of_periods=1,
                    period=Period.ACC_PERIOD_DAY,
                    period_start=Period.PERIOD_START_TODAY,
                )
            )
            export_job = ExportJob.objects.create(
                base_path=tmp_dir,
                fs_connector=self.local_fs_connector,
                export_strategy=export_strategy,
            )
            export_job.run()
            filepath = os.path.join(tmp_dir, 'pivot_table_2021-09-26-2021-09-26.xlsx')
            self.assertTrue(os.path.exists(filepath))
            self.assertTrue(os.path.getsize(filepath) > 0)

    @freeze_time('2021-09-26')
    def test_export_plan_and_fact_hours(self):
        employment = EmploymentFactory()
        dt_now = date.today()
        self._create_worker_day(
            employment=employment,
            dttm_work_start=datetime.combine(dt_now, time(10, 00)),
            dttm_work_end=datetime.combine(dt_now, time(20, 00)),
            is_approved=True,
            is_fact=True,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            export_strategy = SystemExportStrategy.objects.create(
                strategy_type=SystemExportStrategy.PLAN_AND_FACT_HOURS_TABLE,
                period=Period.objects.create(
                    count_of_periods=1,
                    period=Period.ACC_PERIOD_MONTH,
                    period_start=Period.PERIOD_START_CURRENT_MONTH,
                )
            )
            export_job = ExportJob.objects.create(
                base_path=tmp_dir,
                fs_connector=self.local_fs_connector,
                export_strategy=export_strategy,
            )
            export_job.run()
            filepath = os.path.join(tmp_dir, 'plan_and_fact_hours_2021-09-01-2021-09-30.xlsx')
            self.assertTrue(os.path.exists(filepath))
            self.assertTrue(os.path.getsize(filepath) > 0)

class TestExportRetry(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.local_fs_connector = LocalFilesystemConnector.objects.create(
            name='local',
        )
        cls.system_export_strategy = SystemExportStrategy.objects.create(
                strategy_type=SystemExportStrategy.PLAN_AND_FACT_HOURS_TABLE,
                period=Period.objects.create(
                    count_of_periods=1,
                    period=Period.ACC_PERIOD_MONTH,
                    period_start=Period.PERIOD_START_CURRENT_MONTH,
                )
            )
        cls.export_job = ExportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            export_strategy=cls.system_export_strategy,
            retry_attempts=json.dumps({1: 8600, 3: 45}),
        )
    
    @freeze_time('2022-02-16')
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @mock.patch.object(Task, 'retry', side_effect=Task.retry, autospec=Task.retry) # чтобы отследить вызовы, не трогая функционал
    @mock.patch.object(ExportJob, 'run', side_effect=Exception())
    @mock.patch('celery.app.task.Context.called_directly', new_callable=mock.PropertyMock)
    def test_retry(self, called_directly, mock_run, mock_retry):
        dttm = datetime(2022, 2, 16)
        called_directly.return_value = False
        run_export_job.delay(self.export_job.id)
        self.assertEqual(mock_retry.call_count, 4)
        mock_retry.assert_has_calls(
            [
                mock.call(mock.ANY, max_retries=3, eta=dttm + timedelta(seconds=8600), exc=mock.ANY),
                mock.call(mock.ANY, max_retries=3, eta=dttm + timedelta(seconds=3600), exc=mock.ANY),
                mock.call(mock.ANY, max_retries=3, eta=dttm + timedelta(seconds=45), exc=mock.ANY),
                mock.call(mock.ANY, max_retries=3, eta=dttm + timedelta(seconds=3600), exc=mock.ANY),
            ]
        )
        mock_retry.reset_mock()
        mock_run.side_effect = [Exception(), 'OK']
        run_export_job.delay(self.export_job.id)
        self.assertEqual(mock_retry.call_count, 1)
