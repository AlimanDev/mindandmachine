import json
import os

from django.conf import settings
from django.db.models import Sum
from django.test import TestCase
from freezegun import freeze_time

from src.base.tests.factories import (
    ShopFactory,
    NetworkFactory,
)
from src.exchange.models import SystemImportStrategy, ImportJob, LocalFilesystemConnector
from src.forecast.models import (
    Receipt,
    PeriodClients,
    OperationTypeName,
    OperationType,
)
from src.forecast.receipt.tasks import (
    aggregate_timeserie_value,
)
from src.integration.models import GenericExternalCode
from src.util.mixins.tests import TestsHelperMixin


class TestImportData(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(
            code='pobeda',
            settings_values=json.dumps({
                'receive_data_info': [
                    {
                        'update_gap': 30,
                        'grouping_period': 'h1',
                        'aggregate': [
                            {
                                'timeserie_code': 'bills_count',
                                'timeserie_action': 'nunique',
                                # 'timeserie_value': 'Номер чека',
                                'timeserie_value_complex': ['Номер чека', 'Номер кассы id', 'Дата время открытия чека'],
                            },
                            {
                                'timeserie_code': 'goods_count',
                                'timeserie_action': 'sum',
                                'timeserie_value': 'Количество товара: суммарно по 1 SKU либо 1 единицы SKU',
                            },
                        ],
                        'data_type': 'purchases'
                    }
                ]
            })
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

        cls.local_fs_connector = LocalFilesystemConnector.objects.create(
            name='local',
        )
        cls.import_shop_mapping_strategy = SystemImportStrategy.objects.create(
            strategy_type=SystemImportStrategy.POBEDA_IMPORT_SHOP_MAPPING,
            settings_json=cls.dump_data(dict(
                filename=os.path.join('src', 'exchange', 'tests', 'files', 'division.xlsx'),  # можно относительный путь
                shop_code_1s_field_name='GUID в 1С',
                shop_number_run_field_name='Код магазина',
            )),
        )
        cls.import_purchases_strategy = SystemImportStrategy.objects.create(
            strategy_type=SystemImportStrategy.POBEDA_IMPORT_PURCHASES,
        )
        cls.import_brak_strategy = SystemImportStrategy.objects.create(
            strategy_type=SystemImportStrategy.POBEDA_IMPORT_BRAK,
        )
        cls.import_delivery_strategy = SystemImportStrategy.objects.create(
            strategy_type=SystemImportStrategy.POBEDA_IMPORT_DELIVERY,
        )
        cls.import_shop_mapping_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_shop_mapping_strategy,
        )
        cls.import_purchases_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_purchases_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files')
        )
        cls.import_brak_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_brak_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files')
        )
        cls.import_delivery_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_delivery_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files')
        )

    @freeze_time('2021-09-14')
    def test_import_shop_mapping_then_import_hist_data_into_receipt_then_aggregate_period_clients(self):
        import_shop_mapping_results = self.import_shop_mapping_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='pobeda').count(), 3)
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop1.id,
            external_system__code='pobeda',
            code='498').exists())
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop2.id,
            external_system__code='pobeda',
            code='482').exists())
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop3.id,
            external_system__code='pobeda',
            code='194').exists())

        self.assertEqual(len(import_shop_mapping_results.get('errors')), 1)
        self.assertEqual(import_shop_mapping_results['errors'][0], 'no shop with code="Код, которого нету"')

        self.import_shop_mapping_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='pobeda').count(), 3)

        # при повторном запуске столько же
        self.import_shop_mapping_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='pobeda').count(), 3)

        # загрузка исторических данных
        import_purchases_results = self.import_purchases_job.run()
        self.assertEqual(len(import_purchases_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop3.id, data_type='purchases').count(), 616)

        # при повторном запуске столько же
        self.import_purchases_job.run()
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop3.id, data_type='purchases').count(), 616)

        import_brak_results = self.import_brak_job.run()
        self.assertEqual(len(import_brak_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop3.id, data_type='brak').count(), 23)

        import_delivery_results = self.import_delivery_job.run()
        self.assertEqual(len(import_delivery_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop2.id, data_type='delivery').count(), 49)

        aggregate_timeserie_value()
        self.assertEqual(PeriodClients.objects.count(), 2)  # за 1 час для 2 типов операций
        pc_sums = dict(PeriodClients.objects.values(
            'operation_type__operation_type_name__code',
        ).annotate(
            value_sum=Sum('value'),
        ).values_list('operation_type__operation_type_name__code', 'value_sum'))
        self.assertEqual(pc_sums['bills_count'], 105)
        self.assertEqual(pc_sums['goods_count'], 891.76)
