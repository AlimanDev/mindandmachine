import json
import os
from datetime import datetime, timedelta
from unittest import mock

from celery.app.task import Task
from django.conf import settings
from django.db.models import Sum
from django.test import TestCase, override_settings
from freezegun import freeze_time
from src.base.tests.factories import NetworkFactory, ShopFactory
from src.exchange.models import (
    ImportHistDataStrategy,
    ImportJob,
    ImportShopMappingStrategy,
    LocalFilesystemConnector,
)
from src.exchange.tasks import run_import_job
from src.forecast.models import OperationType, OperationTypeName, PeriodClients, Receipt
from src.forecast.receipt.tasks import aggregate_timeserie_value
from src.integration.models import GenericExternalCode
from src.util.mixins.tests import TestsHelperMixin


class TestPobedaImportData(TestsHelperMixin, TestCase):
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
        cls.import_shop_mapping_strategy = ImportShopMappingStrategy.objects.create(
            system_code='pobeda',
            system_name='pobeda',
            filename=os.path.join('src', 'exchange', 'tests', 'files', 'pobeda', 'division.xlsx'),
            file_format='xlsx',
            wfm_shop_code_field_name='GUID в 1С',
            external_shop_code_field_name='Код магазина',
        )
        cls.import_purchases_strategy = ImportHistDataStrategy.objects.create(
            system_code='pobeda',
            data_type='purchases',
            fix_date=True,
            filename_fmt='{data_type}_{year:04d}{month:02d}{day:02d}.csv',
            columns=[
                'Номер магазина id',
                'Номер кассы id',
                'Номер чека',
                'Дата время открытия чека',
                'Дата время закрытия чека',
                'Табель кассира (сотрудника) id',
                'Id SKU',
                'Количество товара: суммарно по 1 SKU либо 1 единицы SKU',
                'Единица измерения',
                'Стоимость SKU: суммарно по 1 SKU либо 1 единицы SKU',
                'Способ оплаты: нал/безнал',
                'Наличие бонусной карты',
            ],
            shop_num_column_name='Номер магазина id',
            dt_or_dttm_column_name='Дата время открытия чека',
            dt_or_dttm_format='%d.%m.%Y %H:%M:%S',
        )
        cls.import_brak_strategy = ImportHistDataStrategy.objects.create(
            system_code='pobeda',
            data_type='brak',
            fix_date=True,
            filename_fmt='{data_type}_{year:04d}{month:02d}{day:02d}.csv',
            columns=[
                'Какой-то guid',
                'Номер магазина id',
                'Дата',
                'Тип списания',
                'Id SKU',
                'Количество товара',
            ],
            shop_num_column_name='Номер магазина id',
            dt_or_dttm_column_name='Дата',
            dt_or_dttm_format='%d.%m.%Y',
            receipt_code_columns=[
                'Какой-то guid',
                'Id SKU',
            ],
        )
        cls.import_delivery_strategy = ImportHistDataStrategy.objects.create(
            system_code='pobeda',
            data_type='delivery',
            fix_date=True,
            filename_fmt='{data_type}_{year:04d}{month:02d}{day:02d}.csv',
            columns=[
                'Какой-то guid',
                'Номер магазина id',
                'Дата и время',
                'Тип поставки',
                'Id SKU',
                'Количество товара',
            ],
            shop_num_column_name='Номер магазина id',
            dt_or_dttm_column_name='Дата и время',
            dt_or_dttm_format='%d.%m.%Y %H:%M:%S',
            receipt_code_columns=[
                'Какой-то guid',
                'Id SKU',
            ],
        )
        cls.import_shop_mapping_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_shop_mapping_strategy,
        )
        cls.import_purchases_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_purchases_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'pobeda')
        )
        cls.import_brak_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_brak_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'pobeda')
        )
        cls.import_delivery_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_delivery_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'pobeda')
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
        self.assertEqual(import_shop_mapping_results['errors'][0], 'no shop with code/name="Код, которого нету"')

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


class TestAmbarImportData(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(
            code='ambar',
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
        cls.shop1 = ShopFactory(code='1', name=cls.shop1_code)
        cls.shop2_code = '07e6d8fc-87d9-11eb-80bb-0050568a6492'
        cls.shop2 = ShopFactory(code='2', name=cls.shop2_code)
        cls.shop3_code = '938e3dcd-6824-11ea-80e8-0050568ab54f'
        cls.shop3 = ShopFactory(code='3', name=cls.shop3_code)
        cls.otn_bills_count = OperationTypeName.objects.create(
            network=cls.network,
            name='Количество чеков',
            code='Sales',
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
        cls.import_shop_mapping_strategy = ImportShopMappingStrategy.objects.create(
            system_code='ambar',
            filename=os.path.join('src', 'exchange', 'tests', 'files', 'ambar', 'shops_mapping.xlsx'),
            file_format='xlsx',
            wfm_shop_name_field_name='Название в ЗУП',
            external_shop_code_field_name='Код объекта (если есть в сети)',
        )
        cls.import_sales_strategy = ImportHistDataStrategy.objects.create(
            system_code='ambar',
            data_type='Sales',
            separated_file_for_each_shop=True,
            filename_fmt='{data_type}_{shop_code}_{year:04d}-{month:02d}-{day:02d}.csv',
            shop_num_column_name='Код магазина',
            dt_or_dttm_column_name='Дата создания',
            dt_or_dttm_format='%Y-%m-%d %H:%M:%S.%f',
        )
        cls.import_delivery_strategy = ImportHistDataStrategy.objects.create(
            system_code='ambar',
            data_type='Delivery',
            filename_fmt='{data_type}_{year:04d}-{month:02d}-{day:02d}.csv',
            shop_num_column_name='Код магазина',
            dt_or_dttm_column_name='Дата',
            dt_or_dttm_format='%Y-%m-%d',
        )
        cls.import_writeoffs_strategy = ImportHistDataStrategy.objects.create(
            system_code='ambar',
            data_type='WriteOff',
            filename_fmt='{data_type}_{year:04d}-{month:02d}-{day:02d}.csv',
            shop_num_column_name='Код магазина',
            dt_or_dttm_column_name='Дата',
            dt_or_dttm_format='%Y-%m-%d',
        )
        cls.import_price_changes_strategy = ImportHistDataStrategy.objects.create(
            system_code='ambar',
            data_type='PriceChanges',
            filename_fmt='{data_type}_{year:04d}-{month:02d}-{day:02d}.csv',
            shop_num_column_name='Код магазина',
            dt_or_dttm_column_name='Дата',
            dt_or_dttm_format='%Y-%m-%d',
        )
        cls.import_open_orders_strategy = ImportHistDataStrategy.objects.create(
            system_code='ambar',
            data_type='OpenOrders',
            filename_fmt='{data_type}_{year:04d}-{month:02d}-{day:02d}.csv',
            shop_num_column_name='Код магазина',
            dt_or_dttm_column_name='Дата поставки',
            dt_or_dttm_format='%Y-%m-%d',
        )
        cls.import_error_strategy = ImportHistDataStrategy.objects.create(
            system_code='ambar',
            data_type='Error',
            filename_fmt='{data_type}_{year:04d}-{month:02d}-{day:02d}.csv',
            shop_num_column_name='Код магазина',
            dt_or_dttm_column_name='Дата создания',
            dt_or_dttm_format='%Y-%m-%d %H:%M:%S.%f',
        )
        cls.import_shop_mapping_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_shop_mapping_strategy,
        )
        cls.import_sales_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_sales_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'ambar')
        )
        cls.import_delivery_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_delivery_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'ambar')
        )
        cls.import_writeoffs_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_writeoffs_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'ambar')
        )
        cls.import_price_changes_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_price_changes_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'ambar')
        )
        cls.import_open_orders_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_open_orders_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'ambar')
        )
        cls.import_error_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_error_strategy,
            base_path=os.path.join(settings.BASE_DIR, 'src', 'exchange', 'tests', 'files', 'ambar')
        )

    @freeze_time('2021-11-13')
    def test_import_shop_mapping_then_import_hist_data_into_receipt_then_aggregate_period_clients(self):
        import_shop_mapping_results = self.import_shop_mapping_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='ambar').count(), 3)
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop1.id,
            external_system__code='ambar',
            code='498').exists())
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop2.id,
            external_system__code='ambar',
            code='482').exists())
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop3.id,
            external_system__code='ambar',
            code='194').exists())

        self.assertEqual(len(import_shop_mapping_results.get('errors')), 1)
        self.assertEqual(import_shop_mapping_results['errors'][0], 'no shop with code/name="Название, которого нету"')

        # при повторном запуске столько же
        self.import_shop_mapping_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='ambar').count(), 3)

        # импорт исторических данных
        import_sales_results = self.import_sales_job.run()
        self.assertEqual(len(import_sales_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(data_type='Sales').count(), 3)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop3.id, data_type='Sales').count(), 1)

        import_delivery_results = self.import_delivery_job.run()
        self.assertEqual(len(import_delivery_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(data_type='Delivery').count(), 1)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop3.id, data_type='Delivery').count(), 1)

        import_writeoffs_results = self.import_writeoffs_job.run()
        self.assertEqual(len(import_writeoffs_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(data_type='WriteOff').count(), 1)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop2.id, data_type='WriteOff').count(), 1)

        import_price_changes_results = self.import_price_changes_job.run()
        self.assertEqual(len(import_price_changes_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(data_type='PriceChanges').count(), 1)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop2.id, data_type='PriceChanges').count(), 1)

        import_open_orders_results = self.import_open_orders_job.run()
        self.assertEqual(len(import_open_orders_results.get('errors')), 0)
        self.assertEqual(Receipt.objects.filter(data_type='OpenOrders').count(), 1)
        self.assertEqual(Receipt.objects.filter(shop_id=self.shop3.id, data_type='OpenOrders').count(), 1)
    
    @freeze_time('2021-11-13')
    def test_import_hist_data_error(self):
        """Не удалось найти файл (напр. пропущен день в исторических данных)"""

        import_error_results = self.import_error_job.run()
        self.assertEqual(len(import_error_results.get('errors')), 1)
        self.assertIn(
            f'Error_2021-11-13.csv',
            import_error_results['errors'][0]
        )

class TestImportRetry(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.local_fs_connector = LocalFilesystemConnector.objects.create(
            name='local',
        )
        cls.import_shop_mapping_strategy = ImportShopMappingStrategy.objects.create(
            system_code='',
            filename='',
            file_format='xlsx',
            wfm_shop_name_field_name='',
            external_shop_code_field_name='',
        )
        cls.import_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_shop_mapping_strategy,
            retry_attempts=json.dumps({1: 8600, 3: 45}),
        )
    
    @freeze_time('2022-02-16')
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @mock.patch.object(Task, 'retry', side_effect=Task.retry, autospec=Task.retry) # чтобы отследить вызовы, не трогая функционал
    @mock.patch.object(ImportJob, 'run', side_effect=Exception())
    @mock.patch('celery.app.task.Context.called_directly', new_callable=mock.PropertyMock)
    def test_retry(self, called_directly, mock_run, mock_retry):
        dttm = datetime(2022, 2, 16)
        called_directly.return_value = False
        run_import_job.delay(self.import_job.id)
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
        run_import_job.delay(self.import_job.id)
        self.assertEqual(mock_retry.call_count, 1)
