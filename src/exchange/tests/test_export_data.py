import tempfile
from datetime import datetime, time, date

from freezegun import freeze_time
from django.test import TestCase
import os
from src.base.tests.factories import (
    ShopFactory,
    NetworkFactory,
    EmploymentFactory,
)
from src.exchange.models import SystemExportStrategy, ExportJob, LocalFilesystemConnector
from src.forecast.models import (
    OperationTypeName,
    OperationType,
)
from src.reports.models import Period
from src.util.mixins.tests import TestsHelperMixin


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
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, f'pivot_table_2021-09-26-2021-09-26.xlsx')))

# User
# Shop
# Employment
# WorkerDay
# Timesheet (вместо него сводной таблицы достаточно?)
