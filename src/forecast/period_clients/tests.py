from src.forecast.models import (
    PeriodClients, 
    OperationType, 
    OperationTypeName,
    WorkType, 
)
from src.timetable.models import (
    Event, 
    WorkTypeName,
)

from src.util.models_converter import Converter

from datetime import datetime, timedelta, time
from django.apps import apps
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.base.models import FunctionGroup
import pandas, io


class TestDemand(APITestCase):

    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/period_clients/'

        create_departments_and_users(self)
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='PeriodClients',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='PeriodClients_put',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='DELETE',
            func='PeriodClients_delete',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='PeriodClients_upload',
            level_up=1,
            level_down=99,
        )

        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        self.work_type_name2 = WorkTypeName.objects.create(
            name='Торговый зал',
        )
        self.work_type_name3 = WorkTypeName.objects.create(
            name='Кассы3',
        )
        self.work_type_name4 = WorkTypeName.objects.create(
            name='Кассы4',
        )
        self.work_type_name5 = WorkTypeName.objects.create(
            name='Кассы5',
        )
        self.work_type1 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name1)
        self.work_type2 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name2)
        self.work_type3 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name3)
        self.work_type4 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name4)
        self.work_type5 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name5)
        
        self.date = datetime.now().date() + timedelta(days=1)
        op_type_name = OperationTypeName.objects.create(
            name='O_TYPE',
        )
        op_type_name2 = OperationTypeName.objects.create(
            name='O_TYPE2',
        )
        op_type_name3 = OperationTypeName.objects.create(
            name='O_TYPE3',
        )
        op_type_name4 = OperationTypeName.objects.create(
            name='O_TYPE4',
        )
        op_type_name5 = OperationTypeName.objects.create(
            name='O_TYPE5',
        )
        self.o_type_1 = OperationType.objects.create(
            work_type=self.work_type1,
            operation_type_name=op_type_name,
            do_forecast=OperationType.FORECAST,
            shop=self.work_type1.shop,
            )
        self.o_type_2 = OperationType.objects.create(
            work_type=self.work_type2,
            operation_type_name=op_type_name4,
            shop=self.work_type2.shop,
            )
        self.o_type_3 = OperationType.objects.create(
            work_type=self.work_type3,
            operation_type_name=op_type_name3,
            do_forecast=OperationType.FORECAST,
            shop=self.work_type3.shop,
            )
        self.o_type_4 = OperationType.objects.create(
            work_type=self.work_type5,
            operation_type_name=op_type_name2,
            shop=self.work_type5.shop,
            )
        self.o_type_5 = OperationType.objects.create(
            work_type=self.work_type4,
            operation_type_name=op_type_name5,
            shop=self.work_type4.shop,
            )
        test_data = {
            'PeriodClients': [
                {
                    'dttm_forecast':datetime(2018, 5, 7, 0, 0),
                    'operation_type':self.o_type_1,
                    'value':20
                },
                {
                    'dttm_forecast':datetime(2018, 5, 7, 0, 0),
                    'operation_type':self.o_type_2,
                    'value':10
                },
                {
                    'dttm_forecast':datetime(2018, 5, 7, 0, 0),
                    'operation_type':self.o_type_3,
                    'value':30
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_1,
                    'value':30
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_2,
                    'value':20
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_3,
                    'value':5
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_1,
                    'value':15,
                    'type':PeriodClients.FACT_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_2,
                    'value':19,
                    'type':PeriodClients.FACT_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_3,
                    'value':5,
                    'type':PeriodClients.FACT_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_1,
                    'value':12,
                    'type':PeriodClients.SHORT_FORECAST_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_2,
                    'value':10,
                    'type':PeriodClients.SHORT_FORECAST_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':self.o_type_3,
                    'value':6,
                    'type':PeriodClients.SHORT_FORECAST_TYPE
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(12, 0)),
                    'operation_type' : self.o_type_4,
                    'value' : 10
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(12, 30)),
                    'operation_type' : self.o_type_4,
                    'value' : 20
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(13, 0)),
                    'operation_type' : self.o_type_4,
                    'value' : 15
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(13, 30)),
                    'operation_type' : self.o_type_4,
                    'value' : 10
                },
                {
                    'dttm_forecast' : datetime.combine(self.date + timedelta(days=1), time(13, 0)),
                    'operation_type' : self.o_type_4,
                    'value' : 10
                }
            ]
        }
        self.o_types = [self.o_type_1, self.o_type_2, self.o_type_3, self.o_type_4, self.o_type_5]
        for model in test_data.keys():
            for data in test_data[model]:
                apps.get_model('forecast', model).objects.create(**data)

        self.create_data = {
            "status": "R",
            "demand": [
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 10)),
                    "value": 2.1225757598876953,
                    "work_type": self.o_type_5.id,
                },
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 10, 30)),
                    "value": 2.2346010208129883,
                    "work_type": self.o_type_5.id,
                },
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 11)),
                    "value": 2.195962905883789,
                    "work_type": self.o_type_5.id,
                },
                {
                    "dttm": Converter.convert_datetime(datetime(2019, 9, 1, 11, 30)),
                    "value": 2.307988166809082,
                    "work_type": self.o_type_5.id,
                },
            ],
            "dt_from": Converter.convert_date(datetime(2019, 9, 1)),
            "dt_to": Converter.convert_date(datetime(2019, 11, 2)),
            "shop_id": self.shop.id,
        }
        self.data = {
            'from_dttm' : Converter.convert_datetime(datetime.combine(self.date, time(12, 0))),
            'to_dttm' : Converter.convert_datetime(datetime.combine(self.date + timedelta(days=1), time(13, 0))),
            'shop_id' : self.shop.id,
            'type': 'L',
        }

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
                'value': 2.1225757598877, 
                'operation_type_id': self.o_type_5.id, 
                'type': 'L'
            }, 
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 30), 
                'value': 2.23460102081299, 
                'operation_type_id': self.o_type_5.id, 
                'type': 'L'
            }, 
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 0), 
                'value': 2.19596290588379, 
                'operation_type_id': self.o_type_5.id, 
                'type': 'L'
            }, 
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 30), 
                'value': 2.30798816680908, 
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
        #self.assertEqual(Event.objects.first().text, f'Cоставлен новый спрос на период с {Converter.convert_date(datetime(2019, 9, 1))} по {Converter.convert_date(datetime(2019, 11, 2))}')

    def test_create_fact(self):
        
        self.create_data['type'] = 'F'
        test_data = {
            "data": json.dumps(self.create_data),
        }

        response = self.client.post(self.url, test_data)

        correct_data = [
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 0), 
                'value': 2.1225757598877, 
                'operation_type_id': self.o_type_5.id, 
                'type': 'F'
            }, 
            {
                'dttm_forecast': datetime(2019, 9, 1, 10, 30), 
                'value': 2.23460102081299, 
                'operation_type_id': self.o_type_5.id, 
                'type': 'F'
            }, 
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 0), 
                'value': 2.19596290588379, 
                'operation_type_id': self.o_type_5.id, 
                'type': 'F'
            }, 
            {
                'dttm_forecast': datetime(2019, 9, 1, 11, 30), 
                'value': 2.30798816680908, 
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
            ).order_by('dttm_forecast').values('dttm_forecast', 'value').distinct()[:5].values_list('value', flat=True)), 
            correct_data
        )

    def test_update_value_operation(self):
        for op in self.o_types:
            op.dttm_added = datetime.combine(self.date, time(12, 0))
            op.save()
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
                dttm_forecast = datetime.combine(self.date, time(13, 30)),
                operation_type = self.o_types[3]
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
        response = self.client.get(f'{self.url}indicators/?dt_from={Converter.convert_date(datetime(2018, 5, 6))}&dt_to={Converter.convert_date(datetime(2018, 6, 8))}&shop_id={self.shop.id}')
        self.assertEqual(
            {
                'overall_operations': 0.115, 
                'fact_overall_operations': 0.039,
            },
            response.json()
        )


    # Сервер для обработки алгоритма недоступен.
    def test_upload_demand(self):

        file = open('etc/scripts/demand.xlsx', 'rb')
        response = self.client.post(f'{self.url}upload/', {'shop_id': 1, 'file': file})
        file.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PeriodClients.objects.filter(
                operation_type__work_type__work_type_name__in=[self.work_type_name1, self.work_type_name2],
                dttm_forecast__date__gte=datetime(2020, 4, 30),
                dttm_forecast__date__lte=datetime(2020, 5, 1),
            ).count(), 
            40
        )


    def test_get_demand_xlsx(self):

        response = self.client.get(f'{self.url}download/?dt_from={Converter.convert_date(datetime(2019, 5, 30).date())}&dt_to={Converter.convert_date(datetime(2019, 6, 2).date())}&shop_id={self.shop.id}')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[0]][0], 'Кассы O_TYPE')
        self.assertEqual(tabel[tabel.columns[1]][0], '30.05.2019 00:00:00')
