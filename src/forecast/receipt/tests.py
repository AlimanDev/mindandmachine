import json

from rest_framework.test import APITestCase

from src.base.models import FunctionGroup
from src.forecast.factories import ReceiptFactory
from src.util.mixins.tests import TestsHelperMixin


class TestReceiptCreateAndUpdate(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.network = cls.user1.network
        cls.network.settings_values = json.dumps({
            'receive_data_info': [
                {
                    'update_gap': 15,
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

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def _get_data(self):
        return {
            "Ссылка": "954a22a1-cd84-11ea-8edf-00155d012a03",
            "Дата": "2020-07-24T11:06:32",
            "ТабельныйНомер": "НМЗН-03312",
            "ФИОПродавца": "Безносикова Светлана Павловна",
            "КодМагазина": self.shop.code,
            "Guidзаказа": "00000000-0000-0000-0000-000000000000",
            "Номер": "RM-00501946",
            "ВидОперации": "Продажа",
            "ДисконтнаяКарта": "S03058    ",
            "ФизЛицо": "f0444dea-05da-11ea-8d9a-00155d01831d",
            "Магазин": "3669648",
            "ТипЗаказа": "Продажа салона",
            "КоличествоТоваровВЧеке": "1",
            "СуммаДокумента": "1323",
            "КодКупона": "",
            "Товары": [
                {
                    "Нкод": "Ц0000000021",
                    "Хкод": "Х0010319",
                    "Количество": "1",
                    "Цена": "1890",
                    "СуммаБонус": "0",
                    "СуммаСкидки": "567",
                    "Сумма": "1323",
                    "id": "1",
                    "Скидки": [
                        {
                            "СкидкаНаценка": "Скидка сотруднику_НМ"
                        }
                    ],
                    "КоличествоБонусов": "0",
                    "ДатаНачисления": "0001-01-01T00:00:00",
                    "ДатаСписания": "0001-01-01T00:00:00"
                }
            ]
        }

    def test_create_receipt(self):
        resp = self.client.post(
            path=self.get_url('Receipt-list'),
            data=self.dump_data({'data': [self._get_data()], 'data_type': 'Чек'}), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)

    def test_update_receipt(self):
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='Receipt',
            level_up=1,
            level_down=99,
        )

        receipt = ReceiptFactory(
            shop=self.shop,
            info=self.dump_data({}),
            data_type='Чек',
        )
        resp = self.client.put(
            path=self.get_url('Receipt-detail', pk=receipt.pk),
            data=self.dump_data({'data': self._get_data(), 'data_type': 'Чек'}), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
