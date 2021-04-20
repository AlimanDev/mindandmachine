import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from src.forecast.receipt.tasks import (
    aggregate_timeserie_value,
    clean_timeserie_actions,
)
from src.forecast.models import (
    OperationTypeName,
    OperationType,
    Receipt,
    PeriodClients,
)
from src.forecast.tests.factories import ReceiptFactory
from src.util.mixins.tests import TestsHelperMixin


class TestAggregateTimeserie(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.network.settings_values = json.dumps({
            'receive_data_info': [
                {
                    'update_gap': 30,
                    'delete_gap': 20,
                    'grouping_period': 'h1',
                    'aggregate': [
                        {
                            'timeserie_code': 'bills',
                            'timeserie_action': 'count',
                            'timeserie_value': 'СуммаДокумента',
                            'timeserie_filters': {
                                'ВидОперации': 'Продажа',
                            },
                        },
                        {
                            'timeserie_code': 'income',
                            'timeserie_action': 'sum',
                            'timeserie_value': 'СуммаДокумента',
                            'timeserie_filters': {
                                'ВидОперации': 'Продажа',
                            },
                        },
                    ],
                    'shop_code_field_name': 'КодМагазина',
                    'receipt_code_field_name': 'Ссылка',
                    'dttm_field_name': 'Дата',
                    'data_type': 'Чек'
                }
            ]
        })
        cls.network.save()
        cls.op_type_name = OperationTypeName.objects.create(
            name='чеки',
            code='bills',
            network=cls.network,
        )
        cls.op_type_name2 = OperationTypeName.objects.create(
            name='выручка',
            code='income',
            network=cls.network,
        )
        cls.op_type = OperationType.objects.create(
            shop=cls.shop,
            operation_type_name=cls.op_type_name,
        )
        cls.op_type2 = OperationType.objects.create(
            shop=cls.shop,
            operation_type_name=cls.op_type_name2,
        )
        ReceiptFactory.create_batch(
            10, shop=cls.shop, data_type='Чек', info='{"СуммаДокумента": 100, "ВидОперации": "Продажа"}')
        ReceiptFactory.create_batch(
            5, shop=cls.shop, data_type='Чек', info='{"СуммаДокумента": 100, "ВидОперации": "Возврат"}'
        )

    def setUp(self):
        self.network.refresh_from_db()

    def test_aggregate_timeserie_value_task_with_filters(self):
        aggregate_timeserie_value()
        income_sum = sum(PeriodClients.objects.filter(
            operation_type=self.op_type2, type=PeriodClients.FACT_TYPE).values_list('value', flat=True))
        self.assertEqual(income_sum, 1000)

    def test_aggregate_timeserie_value_task_without_filters(self):
        settings_values_dict = json.loads(self.network.settings_values)
        settings_values_dict['receive_data_info'][0]['aggregate'][0]['timeserie_filters'] = None
        settings_values_dict['receive_data_info'][0]['aggregate'][1]['timeserie_filters'] = None
        self.network.settings_values = json.dumps(settings_values_dict)
        self.network.save()
        aggregate_timeserie_value()
        income_sum = sum(PeriodClients.objects.filter(
            operation_type=self.op_type2, type=PeriodClients.FACT_TYPE).values_list('value', flat=True))
        self.assertEqual(income_sum, 1500)

    def test_clean_timeserie_actions(self):
        initial_receipts_count = Receipt.objects.count()
        old_receipts_count = 5
        ReceiptFactory.create_batch(
            old_receipts_count, shop=self.shop, data_type='Чек', dttm=timezone.now() - timedelta(days=60))
        clean_timeserie_actions()
        self.assertEqual(initial_receipts_count, Receipt.objects.count())
