import json
from copy import deepcopy
from datetime import datetime
from datetime import timedelta, time

import io
import pandas
from rest_framework.test import APITestCase
from rest_framework import status

from src.apps.forecast.models import (
    PeriodClients,
    OperationType,
    OperationTypeName,
    WorkType,
)
from src.apps.base.models import Shop
from src.apps.forecast.period_clients.utils import create_demand
from src.apps.timetable.models import (
    WorkTypeName,
)
from src.common.mixins.tests import TestsHelperMixin
from src.common.models_converter import Converter


class TestDemand(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/period_clients/'

        cls.create_departments_and_users()

        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            code="Cashbox",
            network=cls.network,
        )
        cls.work_type_name2 = WorkTypeName.objects.create(
            name='Торговый зал',
            code="Trade hall",
            network=cls.network,
        )
        cls.work_type_name3 = WorkTypeName.objects.create(
            name='Кассы3',
            code="Cashbox3",
            network=cls.network,
        )
        cls.work_type_name4 = WorkTypeName.objects.create(
            name='Кассы4',
            code="Cashbox4",
            network=cls.network,
        )
        cls.work_type_name5 = WorkTypeName.objects.create(
            name='Кассы5',
            code="clients",
            network=cls.network,
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.work_type2 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name2)
        cls.work_type3 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name3)
        cls.work_type4 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name4)
        cls.work_type5 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name5)

        cls.date = datetime.now().date() + timedelta(days=1)
        cls.op_type_name = cls.work_type_name1.operation_type_name
        cls.op_type_name2 = cls.work_type_name2.operation_type_name
        cls.o_type_1 = cls.work_type1.operation_type
        cls.o_type_2 = cls.work_type2.operation_type
        cls.o_type_3 = cls.work_type3.operation_type
        cls.o_type_4 = cls.work_type5.operation_type
        cls.o_type_5 = cls.work_type4.operation_type

        test_data = [
            {
                'dttm_forecast': datetime(2018, 5, 7, 0, 0),
                'operation_type': cls.o_type_1,
                'value': 20
            },
            {
                'dttm_forecast': datetime(2018, 5, 7, 0, 0),
                'operation_type': cls.o_type_2,
                'value': 10
            },
            {
                'dttm_forecast': datetime(2018, 5, 7, 0, 0),
                'operation_type': cls.o_type_3,
                'value': 30
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_1,
                'value': 30
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_2,
                'value': 20
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_3,
                'value': 5
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_1,
                'value': 15,
                'type': PeriodClients.FACT_TYPE
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_2,
                'value': 19,
                'type': PeriodClients.FACT_TYPE
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_3,
                'value': 5,
                'type': PeriodClients.FACT_TYPE
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_1,
                'value': 12,
                'type': PeriodClients.SHORT_FORECAST_TYPE
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_2,
                'value': 10,
                'type': PeriodClients.SHORT_FORECAST_TYPE
            },
            {
                'dttm_forecast': datetime(2018, 6, 7, 9, 0),
                'operation_type': cls.o_type_3,
                'value': 6,
                'type': PeriodClients.SHORT_FORECAST_TYPE
            },
            {
                'dttm_forecast': datetime.combine(cls.date, time(12, 0)),
                'operation_type': cls.o_type_4,
                'value': 10
            },
            {
                'dttm_forecast': datetime.combine(cls.date, time(12, 30)),
                'operation_type': cls.o_type_4,
                'value': 20
            },
            {
                'dttm_forecast': datetime.combine(cls.date, time(13, 0)),
                'operation_type': cls.o_type_4,
                'value': 15
            },
            {
                'dttm_forecast': datetime.combine(cls.date, time(13, 30)),
                'operation_type': cls.o_type_4,
                'value': 10
            },
            {
                'dttm_forecast': datetime.combine(cls.date + timedelta(days=1), time(13, 0)),
                'operation_type': cls.o_type_4,
                'value': 10
            }
        ]
        cls.o_types = [cls.o_type_1, cls.o_type_2, cls.o_type_3, cls.o_type_4, cls.o_type_5]
        PeriodClients.objects.bulk_create(
            [
                PeriodClients(dt_report=data['dttm_forecast'].date(), **data)
                for data in test_data
            ]
        )

        cls.create_data = {
            "status": "R",
            "serie": [
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 10)),
                    "value": 2.1225757598876953,
                    "timeserie_id": cls.o_type_5.id,
                },
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 10, 30)),
                    "value": 2.2346010208129883,
                    "timeserie_id": cls.o_type_5.id,
                },
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 11)),
                    "value": 2.195962905883789,
                    "timeserie_id": cls.o_type_5.id,
                },
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 11, 30)),
                    "value": 2.307988166809082,
                    "timeserie_id": cls.o_type_5.id,
                },
            ],
            "dt_from": Converter.convert_date(datetime(2019, 9, 1)),
            "dt_to": Converter.convert_date(datetime(2019, 11, 2)),
            "shop_id": cls.shop.id,
        }
        cls.data = {
            'from_dttm': Converter.convert_datetime(datetime.combine(cls.date, time(12, 0))),
            'to_dttm': Converter.convert_datetime(datetime.combine(cls.date + timedelta(days=1), time(13, 0))),
            'shop_id': cls.shop.id,
            'type': 'L',
        }

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_algo(self):
        test_data = {
            "shop_id": self.shop.id,
            "access_token": "a",
            "key": "a",
            "data": json.dumps(self.create_data),
        }

        response = self.client.post(self.url, test_data)

        correct_data = [
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 0),
                'value': 2.1225757598876953,
                'operation_type_id': self.o_type_5.id,
                'type': 'L'
            },
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 30),
                'value': 2.2346010208129883,
                'operation_type_id': self.o_type_5.id,
                'type': 'L'
            },
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 0),
                'value': 2.195962905883789,
                'operation_type_id': self.o_type_5.id,
                'type': 'L'
            },
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 30),
                'value': 2.307988166809082,
                'operation_type_id': self.o_type_5.id,
                'type': 'L'
            }
        ]
        self.assertEqual(list(PeriodClients.objects.filter(
            dttm_forecast__gte=datetime(2019, 9, 1, 10),
            dttm_forecast__lte=datetime(2019, 9, 1, 11, 30),
            operation_type_id=self.o_type_5.id
        ).values('dttm_forecast', 'value', 'operation_type_id', 'type')), correct_data)
        self.assertEqual(response.status_code, 201)

    def test_create_fact(self):

        self.create_data['type'] = 'F'
        test_data = {
            "data": json.dumps(self.create_data),
        }

        response = self.client.post(self.url, test_data)

        correct_data = [
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 0),
                'value': 2.1225757598876953,
                'operation_type_id': self.o_type_5.id,
                'type': 'F'
            },
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 30),
                'value': 2.2346010208129883,
                'operation_type_id': self.o_type_5.id,
                'type': 'F'
            },
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 0),
                'value': 2.195962905883789,
                'operation_type_id': self.o_type_5.id,
                'type': 'F'
            },
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 30),
                'value': 2.307988166809082,
                'operation_type_id': self.o_type_5.id,
                'type': 'F'
            }
        ]
        self.assertEqual(list(PeriodClients.objects.filter(
            dttm_forecast__gte=datetime(2019, 9, 1, 10),
            dttm_forecast__lte=datetime(2019, 9, 1, 11, 30),
            operation_type_id=self.o_type_5.id
        ).values('dttm_forecast', 'value', 'operation_type_id', 'type')), correct_data)
        self.assertEqual(response.status_code, 201)

    def test_update_value(self):
        for op in self.o_types:
            op.dttm_added = datetime.combine(self.date, time(12, 0))
            op.save()
        self.data['set_value'] = 20
        response = self.client.put(f'{self.url}put/', data=self.data)
        self.assertEqual(response.status_code, 200)
        correct_data = [20.0, 20.0, 20.0, 10.0, 20.0]
        self.assertEqual(
            list(PeriodClients.objects.filter(
                operation_type__work_type__shop_id=self.shop.id,
                dttm_forecast__lte=datetime.combine(self.date + timedelta(days=1), time(13, 0)),
                dttm_forecast__gte=datetime.combine(self.date, time(12, 0))
            ).order_by('dttm_forecast').values('dttm_forecast', 'value').distinct()[:5].values_list('value',
                                                                                                    flat=True)),
            correct_data
        )

    def test_update_value_operation(self):
        for op in self.o_types:
            op.dttm_added = datetime.combine(self.date, time(12, 0))
            op.save()
        self.shop.forecast_step_minutes = '00:30:00'
        self.shop.save()
        self.data['set_value'] = 30
        self.data['operation_type_id'] = [self.o_type_4.id]
        response = self.client.put(f'{self.url}put/', data=self.data)
        date = self.date + timedelta(days=1)
        correct_data = [
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            },
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 30)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            },
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            },
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 30)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 10.0
            },
            {
                'dttm_forecast': datetime.combine(date, time(12, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            },
            {
                'dttm_forecast': datetime.combine(date, time(12, 30)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            },
            {
                'dttm_forecast': datetime.combine(date, time(13, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            }
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(PeriodClients.objects.filter(
            operation_type__work_type__shop_id=self.shop.id,
            operation_type_id=self.o_type_4.id
        ).values('dttm_forecast', 'type', 'operation_type_id', 'value').order_by('dttm_forecast')),
                         correct_data
                         )

    def test_update_mul(self):
        for op in self.o_types:
            op.dttm_added = datetime.combine(self.date, time(12, 0))
            op.save()

        self.data['multiply_coef'] = 0.2
        response = self.client.put(f'{self.url}put/', data=self.data)
        self.assertEqual(response.status_code, 200)
        operations_count_before = PeriodClients.objects.filter(operation_type__work_type__shop_id=self.shop.id).count()
        self.assertEqual(
            PeriodClients.objects.filter(operation_type__work_type__shop_id=self.shop.id).count(),
            operations_count_before
        )
        self.assertEqual(
            PeriodClients.objects.get(
                dttm_forecast=datetime.combine(self.date, time(13, 30)),
                operation_type=self.o_types[3]
            ).value,
            10
        )

    def test_update_mul_operation(self):
        for op in self.o_types:
            op.dttm_added = datetime.combine(self.date, time(12, 0))
            op.save()
        self.data['multiply_coef'] = 2
        self.data['operation_type_id'] = [self.o_type_4.id]
        response = self.client.put(f'{self.url}put/', data=self.data)
        date = self.date + timedelta(days=1)
        correct_data = [
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 20.0
            },
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 30)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 40.0
            },
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 30.0
            },
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 30)),
                'type': 'L', 'operation_type_id': self.o_type_4.id,
                'value': 10.0
            },
            {
                'dttm_forecast': datetime.combine(date, time(13, 0)),
                'type': 'L',
                'operation_type_id': self.o_type_4.id,
                'value': 20.0
            }
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(PeriodClients.objects.filter(
            operation_type__work_type__shop_id=self.shop.id,
            operation_type_id=self.o_type_4.id,
        ).values('dttm_forecast', 'type', 'operation_type_id', 'value').order_by('dttm_forecast')),
                         correct_data
                         )

    def test_get(self):
        query = f'&dt_from={Converter.convert_date(datetime(2018, 6, 7))}' + \
                f'&dt_to={Converter.convert_date(datetime(2018, 6, 7))}&shop_id={self.shop.id}' + \
                f'&operation_type_id__in={self.o_type_1.id},{self.o_type_2.id}'
        response = self.client.get(f'{self.url}?type=L' + query)
        self.assertEqual(
            [{
                'dttm_forecast': Converter.convert_datetime(datetime(2018, 6, 7, 9)),
                'value': 50.0,
            }],
            response.json()
        )
        response = self.client.get(f'{self.url}?type=F' + query)
        self.assertEqual(
            [{
                'dttm_forecast': Converter.convert_datetime(datetime(2018, 6, 7, 9)),
                'value': 34.0,
            }],
            response.json()
        )
        response = self.client.get(f'{self.url}?type=S' + query)
        self.assertEqual(
            [{
                'dttm_forecast': Converter.convert_datetime(datetime(2018, 6, 7, 9)),
                'value': 22.0,
            }],
            response.json()
        )

    def test_delete(self):
        data = {
            'from_dttm': Converter.convert_datetime(datetime(2018, 5, 7, 0)),
            'to_dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)),
            'operation_type_id': [self.o_type_1.id, self.o_type_2.id],
            'type': 'L',
            'shop_id': self.shop.id,
        }
        count_before = PeriodClients.objects.count()
        response = self.client.delete(f'{self.url}delete/', data)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(count_before - PeriodClients.objects.count(), 4)

    def test_indicators(self):
        response = self.client.get(
            f'{self.url}indicators/?dt_from={Converter.convert_date(datetime(2018, 5, 6))}&dt_to={Converter.convert_date(datetime(2018, 6, 8))}&shop_id={self.shop.id}')
        self.assertEqual(
            {
                'overall_operations': 0.115,
                'fact_overall_operations': 0.039,
            },
            response.json()
        )

    # Сервер для обработки алгоритма недоступен.
    def test_upload_demand(self):
        file = open('etc/scripts/demand_new.xlsx', 'rb')
        response = self.client.post(f'{self.url}upload/', {'shop_id': self.shop.id, 'file': file, 'type': 'L'})
        file.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop=self.shop,
                dttm_forecast__date__gte=datetime(2021, 4, 1),
                dttm_forecast__date__lte=datetime(2021, 4, 2),
                type=PeriodClients.LONG_FORECASE_TYPE,
            ).count(),
            130,
        )
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop=self.shop,
                dttm_forecast__date__gte=datetime(2021, 4, 1),
                dttm_forecast__date__lte=datetime(2021, 4, 2),
                type=PeriodClients.FACT_TYPE,
            ).count(),
            0,
        )
        PeriodClients.objects.filter(
            operation_type__shop=self.shop,
            dttm_forecast__date__gte=datetime(2021, 4, 1),
            dttm_forecast__date__lte=datetime(2021, 4, 2),
        ).delete()
        file = open('etc/scripts/demand_new.xlsx', 'rb')
        response = self.client.post(f'{self.url}upload/', {'shop_id': self.shop.id, 'file': file, 'type': 'F'})
        file.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop=self.shop,
                dttm_forecast__date__gte=datetime(2021, 4, 1),
                dttm_forecast__date__lte=datetime(2021, 4, 2),
                type=PeriodClients.LONG_FORECASE_TYPE,
            ).count(),
            0,
        )
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop=self.shop,
                dttm_forecast__date__gte=datetime(2021, 4, 1),
                dttm_forecast__date__lte=datetime(2021, 4, 2),
                type=PeriodClients.FACT_TYPE,
            ).count(),
            130,
        )


    def test_upload_demand_shops_new_format(self):
        self.shop.code = '0123'
        self.shop.save()
        self.shop2.code = '122'
        self.shop2.save()
        for n in OperationTypeName.objects.all():
            OperationType.objects.create(
                operation_type_name=n,
                shop=self.shop2,
            )
        file = open('etc/scripts/demand_new_shops.xlsx', 'rb')
        response = self.client.post(f'{self.url}upload/', {'shop_id': self.shop.id, 'file': file, 'type': 'L'})
        file.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop=self.shop,
                dttm_forecast__date__gte=datetime(2021, 4, 1),
                dttm_forecast__date__lte=datetime(2021, 4, 2),
                type=PeriodClients.LONG_FORECASE_TYPE,
            ).count(),
            130,
        )
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop=self.shop2,
                dttm_forecast__date__gte=datetime(2021, 4, 1),
                dttm_forecast__date__lte=datetime(2021, 4, 2),
                type=PeriodClients.LONG_FORECASE_TYPE,
            ).count(),
            130,
        )

    def test_upload_demand_shops(self):
        file = open('etc/scripts/demand_shops.xlsx', 'rb')
        self.shop.code = '0123'
        self.shop.save()
        self.shop2.code = '122'
        self.shop2.save()
        OperationType.objects.create(
            operation_type_name=self.op_type_name,
            shop=self.shop2,
        )
        response = self.client.post(f'{self.url}upload_demand/', {'file': file, 'type': 'F', 'operation_type_name_id': self.op_type_name.id})
        file.close()
        self.assertEqual(response.json(), [['0123', 20], ['122', 20]])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__shop__in=[self.shop, self.shop2],
                dttm_forecast__date__gte=datetime(2020, 4, 30),
                dttm_forecast__date__lte=datetime(2020, 5, 1),
            ).count(),
            40
        )


    def test_get_demand_xlsx(self):
        dt_from = Converter.convert_date(datetime(2019, 5, 30).date())
        dt_to = Converter.convert_date(datetime(2019, 6, 2).date())
        response = self.client.get(
            f'{self.url}download/?dt_from={dt_from}&dt_to={dt_to}&shop_id={self.shop.id}')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(list(tabel.columns), ['dttm', 'Кассы', 'Торговый зал', 'Кассы3', 'Кассы4', 'Кассы5'])
        self.assertEqual(tabel[tabel.columns[0]][0], datetime(2019, 5, 30))
        self.assertEqual(tabel[tabel.columns[1]][0], 0)
        response = self.client.get(
            f'{self.url}download/?dt_from={dt_from}&dt_to={dt_to}&shop_id={self.shop.id}&operation_type_name_ids={self.op_type_name.id},{self.op_type_name2.id}')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(tabel.columns), ['dttm', 'Кассы', 'Торговый зал'])
        self.assertEqual(tabel[tabel.columns[0]][0], datetime(2019, 5, 30))
        self.assertEqual(tabel[tabel.columns[1]][0], 0)
        response = self.client.get(
            f'{self.url}download/?dt_from={dt_from}&dt_to={dt_to}&shop_id={self.shop.id}&operation_type_ids={self.o_type_1.id},{self.o_type_2.id}')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(list(tabel.columns), ['dttm', 'Кассы', 'Торговый зал'])

    def test_get_demand_xlsx_no_data(self):
        dt_from = Converter.convert_date(datetime(2019, 5, 30).date())
        dt_to = Converter.convert_date(datetime(2019, 6, 2).date())
        OperationType.objects.create(
            operation_type_name=self.op_type_name,
            shop=self.shop2,
        )
        response = self.client.get(
            f'{self.url}download/?dt_from={dt_from}&dt_to={dt_to}&shop_id={self.shop2.id}')
        tabel = pandas.read_excel(response.content)
        tabel.dttm = tabel.dttm.dt.round('s')
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(list(tabel.columns), ['dttm', 'Кассы'])
        self.assertEqual(tabel[tabel.columns[0]][0], datetime(2019, 5, 30))
        self.assertEqual(len(tabel[tabel.columns[0]]), 96)
        self.assertEqual(tabel[tabel.columns[0]][95], datetime(2019, 6, 2, 23))
        self.assertEqual(tabel[tabel.columns[1]][0], 0)
        self.assertEqual(tabel[tabel.columns[1]][72], 0)

    def test_duplicates_dont_created_for_the_same_dttm_forecast_and_operation_type(self):
        initial_pc_count = PeriodClients.objects.count()
        data = {"shop_code": self.shop.code, "type": "F", "dt_from": "2020-11-22", "dt_to": "2020-11-22",
                "serie": [{"dttm": "2020-11-22T11:00:00", "timeserie_code": "clients", "value": 0},
                          {"dttm": "2020-11-22T11:15:00", "timeserie_code": "clients", "value": 2},
                          {"dttm": "2020-11-22T11:30:00", "timeserie_code": "clients", "value": 2},
                          {"dttm": "2020-11-22T11:45:00", "timeserie_code": "clients", "value": 1},
                          {"dttm": "2020-11-22T12:00:00", "timeserie_code": "clients", "value": 0},
                          {"dttm": "2020-11-22T12:15:00", "timeserie_code": "clients", "value": 0},
                          {"dttm": "2020-11-22T12:30:00", "timeserie_code": "clients", "value": 0},
                          {"dttm": "2020-11-22T12:45:00", "timeserie_code": "clients", "value": 0}]}
        create_demand(deepcopy(data))
        self.assertEqual(initial_pc_count + 8, PeriodClients.objects.count())
        create_demand(deepcopy(data))
        self.assertEqual(initial_pc_count + 8, PeriodClients.objects.count())

    def test_create_with_non_existent_operation_type(self):

        test_data = {
            "data": json.dumps(
                {
                    "status": "R",
                    "serie": [
                        {
                            "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 10)),
                            "value": 2.1225757598876953,
                            "timeserie_code": self.o_type_5.operation_type_name.code,
                        },
                        {
                            "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 10)),
                            "value": 2.2346010208129883,
                            "timeserie_code": 'non_existent',
                        }
                    ],
                    "dt_from": Converter.convert_date(datetime(2019, 9, 1)),
                    "dt_to": Converter.convert_date(datetime(2019, 11, 2)),
                    "shop_code": self.shop.code,
                }
            ),
        }

        response = self.client.post(self.url, test_data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        msg = "ValidationError('Operation type with code non_existent does not exist in shop Shop1')"
        self.assertEqual(response.json(), [msg])

        shop_m = Shop.objects.filter(id=self.shop.id).values()[0]
        self.assertEqual(shop_m['load_template_status'], Shop.LOAD_TEMPLATE_ERROR)
