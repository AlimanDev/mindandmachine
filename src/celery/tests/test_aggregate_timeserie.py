import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from src.celery.tasks import (
    aggregate_timeserie_value,
    clean_timeserie_actions,
)
from src.forecast.factories import ReceiptFactory
from src.forecast.models import (
    OperationTypeName,
    OperationType,
)
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
                            'timeserie_value': 'СуммаДокумента'
                        },
                        {
                            'timeserie_code': 'income',
                            'timeserie_action': 'sum',
                            'timeserie_value': 'СуммаДокумента'
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
        for otm in [cls.op_type_name, cls.op_type_name2]:
            OperationType.objects.create(
                shop=cls.shop,
                operation_type_name=otm,
            )
        ReceiptFactory.create_batch(10, shop=cls.shop, data_type='Чек')

    def test_aggregate_timeserie_value_task(self):
        aggregate_timeserie_value()

    def test_clean_timeserie_actions(self):
        ReceiptFactory.create_batch(5, shop=self.shop, data_type='Чек', dttm=timezone.now() - timedelta(days=60))
        clean_timeserie_actions()
