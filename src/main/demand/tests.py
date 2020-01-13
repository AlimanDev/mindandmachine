from src.util.test import LocalTestCase
from src.forecast.models import (
    PeriodClients, 
    OperationType, 
    OperationTypeName,
    WorkType, 
)
from src.timetable.models import (
    Event
)

from src.util.models_converter import Converter

from datetime import datetime, timedelta, time
from django.apps import apps
import json

class TestDemand(LocalTestCase):
    def setUp(self):
        super().setUp()
        self.date = datetime.now().date()
        op_type_name = OperationTypeName.objects.create(
            name='',
            code='',
        )
        w_type = self.work_type1
        w_type_2 = self.work_type4
        def_d = {
                'work_type' :w_type,
                'operation_type_name' : op_type_name,
                'do_forecast' : OperationType.FORECAST_HARD
            }
        def_wf = {
                'work_type' :w_type,
                'operation_type_name' : op_type_name,
            }
        o_type_1 = OperationType.objects.update_or_create(
            id=5,
            defaults=def_d
            )[0]
        o_type_2 = OperationType.objects.update_or_create(
            id=6,
            defaults=def_wf
            )[0]
        o_type_3 = OperationType.objects.update_or_create(
            id=7,
            defaults=def_d
            )[0]
        o_type_4 = OperationType.objects.update_or_create(
            id=8,
            defaults=def_wf
            )[0]
        self.o_type_5 = OperationType.objects.update_or_create(
            id=9,
            defaults={
                'work_type' :w_type_2,
                'operation_type_name' : op_type_name,
            }
            )[0]
        test_data = {
            'PeriodClients': [
                {
                    'dttm_forecast':datetime(2018, 5, 7, 0, 0),
                    'operation_type':o_type_1,
                    'value':20
                },
                {
                    'dttm_forecast':datetime(2018, 5, 7, 0, 0),
                    'operation_type':o_type_2,
                    'value':10
                },
                {
                    'dttm_forecast':datetime(2018, 5, 7, 0, 0),
                    'operation_type':o_type_3,
                    'value':30
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_1,
                    'value':30
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_2,
                    'value':20
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_3,
                    'value':5
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_1,
                    'value':15,
                    'type':PeriodClients.FACT_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_2,
                    'value':19,
                    'type':PeriodClients.FACT_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_3,
                    'value':5,
                    'type':PeriodClients.FACT_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_1,
                    'value':12,
                    'type':PeriodClients.SHORT_FORECAST_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_2,
                    'value':10,
                    'type':PeriodClients.SHORT_FORECAST_TYPE
                },
                {
                    'dttm_forecast':datetime(2018, 6, 7, 9, 0),
                    'operation_type':o_type_3,
                    'value':6,
                    'type':PeriodClients.SHORT_FORECAST_TYPE
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(12, 0)),
                    'operation_type' : o_type_4,
                    'value' : 10
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(12, 30)),
                    'operation_type' : o_type_4,
                    'value' : 20
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(13, 0)),
                    'operation_type' : o_type_4,
                    'value' : 15
                },
                {
                    'dttm_forecast' : datetime.combine(self.date, time(13, 30)),
                    'operation_type' : o_type_4,
                    'value' : 10
                },
                {
                    'dttm_forecast' : datetime.combine(self.date + timedelta(days=1), time(13, 0)),
                    'operation_type' : o_type_4,
                    'value' : 10
                }
            ]
        }
        self.o_types = [o_type_1, o_type_2, o_type_3, o_type_4, self.o_type_5]
        for model in test_data.keys():
            for data in test_data[model]:
                apps.get_model('forecast', model).objects.create(**data)

        
class TestGetIndicators(TestDemand):
    def setUp(self):

        super().setUp()

    def test_correct(self):
        self.auth()

        response = self.api_get(f'/api/demand/get_indicators?from_dt={Converter.convert_date(datetime(2018, 5, 6))}&to_dt={Converter.convert_date(datetime(2018, 6, 8))}&shop_id=13')
        
        self.assertEqual(response.status_code, 200)
        correct_res = {
            'code' : 200,
            'data' : {
                'overall_operations' : 0.115,
                'operations_growth' : 91.66666666666666,
                'fact_overall_operations' : 0.039
            },
            'info' : None
        }
        self.assertEqual(response.json(), correct_res)
    
    def test_data_not_setted(self):
        self.auth()
        response = self.api_get('/api/demand/get_indicators')
        correct_res = {
            'code': 400, 
            'data': {
                'error_type': 'ValueException', 
                'error_message': "[('from_dt', ['This field is required.']), ('to_dt', ['This field is required.']), ('shop_id', ['This field is required.'])]"
            }, 
            'info': None
        }
        self.assertEqual(response.json(), correct_res)


class TestGetForecast(TestDemand):

    def setUp(self):
        super().setUp()

        # test_data = {
        #     'PeriodProducts':[
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[0],
        #             'value' : 13
        #         },
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[1],
        #             'value' : 25
        #         },
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[2],
        #             'value' : 20
        #         },
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[0],
        #             'value' : 12,
        #             'type' : PeriodQueues.FACT_TYPE
        #         },
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[1],
        #             'value' : 25,
        #             'type' : PeriodQueues.FACT_TYPE
        #         },
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[2],
        #             'value' : 9,
        #             'type' : PeriodQueues.FACT_TYPE
        #         },
        #         {
        #             'dttm_forecast': datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[0],
        #             'value' : 15,
        #             'type' : PeriodQueues.SHORT_FORECAST_TYPE
        #         },
        #         {
        #             'dttm_forecast':datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[1],
        #             'value' : 23,
        #             'type' : PeriodQueues.SHORT_FORECAST_TYPE
        #         },
        #         {
        #             'dttm_forecast':datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[2],
        #             'value' : 7,
        #             'type' : PeriodQueues.SHORT_FORECAST_TYPE
        #         }
        #     ],
        #     'PeriodQueues' : [
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[0],
        #             'value' : 4
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[1],
        #             'value' : 50
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[2],
        #             'value' : 21
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[0],
        #             'value' : 5,
        #             'type' : PeriodProducts.FACT_TYPE
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[1],
        #             'value' : 39,
        #             'type' : PeriodProducts.FACT_TYPE
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[2],
        #             'value' : 21,
        #             'type' : PeriodProducts.FACT_TYPE
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[0],
        #             'value' : 4,
        #             'type' : PeriodProducts.SHORT_FORECAST_TYPE
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[1],
        #             'value' : 35,
        #             'type' : PeriodProducts.SHORT_FORECAST_TYPE
        #         },
        #         {
        #             'dttm_forecast' : datetime(2018, 6, 7, 9, 0),
        #             'operation_type' : self.o_types[2],
        #             'value' : 26,
        #             'type' : PeriodProducts.SHORT_FORECAST_TYPE
        #         }
        #     ]
        # }
        # for model in test_data.keys():
        #     for data in test_data[model]:
        #         apps.get_model('db', model).objects.create(**data)

    def test_correct_all_operations(self):
        self.auth()
        
        response = self.api_get(f'/api/demand/get_forecast?from_dt={Converter.convert_date(datetime(2018, 6, 7))}&to_dt={Converter.convert_date(datetime(2018, 6, 7))}&shop_id=13')
        correct_L = {
            'dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)),
            'clients': 55.0, 
            # 'products': 58.0,
            # 'queue': 75.0
        }
        correct_F = {
            'dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)), 
            'clients': 39.0, 
            # 'products': 46.0,
            # 'queue': 65.0
        }
        correct_S = {
            'dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)), 
            'clients': 28.0, 
            # 'products': 45.0,
            # 'queue': 65.0
        }
        self.assertEqual(response.json()['data']['L'][18], correct_L)
        self.assertEqual(response.json()['data']['F'][18], correct_F)
        self.assertEqual(response.json()['data']['S'][18], correct_S)

    def test_correct_some_operations(self):
        self.auth()
        
        response = self.api_get(f'/api/demand/get_forecast?from_dt={Converter.convert_date(datetime(2018, 6, 7))}&to_dt={Converter.convert_date(datetime(2018, 6, 7))}&shop_id=13&operation_type_ids=[5,6]')
        correct_L = {
            'dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)),
            'clients': 50.0, 
            # 'products': 38.0,
            # 'queue': 54.0
        }
        correct_F = {
            'dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)), 
            'clients': 34.0, 
            # 'products': 37.0,
            # 'queue': 44.0
        }
        correct_S = {
            'dttm': Converter.convert_datetime(datetime(2018, 6, 7, 9)), 
            'clients': 22.0, 
            # 'products': 38.0,
            # 'queue': 39.0
        }
        self.assertEqual(response.json()['data']['L'][18], correct_L)
        self.assertEqual(response.json()['data']['F'][18], correct_F)
        self.assertEqual(response.json()['data']['S'][18], correct_S)

    def test_data_not_setted(self):
        self.auth()
        
        response = self.api_get('/api/demand/get_forecast')
        correct_res = {
            'code': 400, 
            'data': {
                'error_type': 'ValueException', 
                'error_message': "[('from_dt', ['This field is required.']), ('to_dt', ['This field is required.']), ('shop_id', ['This field is required.'])]"
            }, 
            'info': None
        }
        self.assertEqual(response.json(), correct_res)

class TestSetDemand(TestDemand):

    def setUp(self):
        super().setUp()
        self.data = {
            'from_dttm' : Converter.convert_datetime(datetime.combine(self.date, time(12, 0))),
            'to_dttm' : Converter.convert_datetime(datetime.combine(self.date + timedelta(days=1), time(13, 0))),
            'shop_id' : 13
        }
        for op in self.o_types:
            op.dttm_added = datetime.combine(self.date, time(12, 0))
            op.save()
    
    def test_correct_coef(self):
        self.auth()
        self.data['multiply_coef'] = 0.2
        response = self.api_post('/api/demand/set_demand', data=self.data) 
        self.assertEqual(response.status_code, 200)
        operations_count_before = PeriodClients.objects.filter(operation_type__work_type__shop_id=13).count()
        self.assertEqual(
            PeriodClients.objects.filter(operation_type__work_type__shop_id=13).count(), 
            operations_count_before
        )
        self.assertEqual(
            PeriodClients.objects.get(
                dttm_forecast = datetime.combine(self.date, time(13, 30)),
                operation_type = self.o_types[3]
            ).value,
            10
        )
    
    def test_correct_val(self):
        self.auth()
        self.data['set_value'] = 20
        response = self.api_post('/api/demand/set_demand', data=self.data)
        self.assertEqual(response.status_code, 200)
        correct_data = [20.0, 20.0, 20.0, 10.0, 20.0]
        self.assertEqual(
            list(PeriodClients.objects.filter(
                operation_type__work_type__shop_id=13,
                dttm_forecast__lte=datetime.combine(self.date + timedelta(days=1), time(13, 0)),
                dttm_forecast__gte=datetime.combine(self.date, time(12, 0))
            ).order_by('dttm_forecast').values('dttm_forecast', 'value').distinct()[:5].values_list('value', flat=True)), 
            correct_data
        )
        
    
    def test_correct_val_operation(self):
        self.auth()
        self.data['set_value'] = 30
        self.data['operation_type_id'] = '[8]'
        response = self.api_post('/api/demand/set_demand', data=self.data)
        date = self.date + timedelta(days=1)
        correct_data = [
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }, 
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 30)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }, 
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }, 
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 30)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 10.0
            }, 
            {
                'dttm_forecast': datetime.combine(date, time(12, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }, 
            {
                'dttm_forecast': datetime.combine(date, time(12, 30)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }, 
            {
                'dttm_forecast': datetime.combine(date, time(13, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(PeriodClients.objects.filter(
                operation_type__work_type__shop_id=13,
                operation_type_id=8
            ).values('dttm_forecast', 'type', 'operation_type_id', 'value').order_by('dttm_forecast')),
            correct_data
        )

    def test_correct_mul_operation(self):
        self.auth()
        self.data['multiply_coef'] = 2
        self.data['operation_type_id'] = '[8]'
        response = self.api_post('/api/demand/set_demand', data=self.data)
        date = self.date + timedelta(days=1)
        correct_data = [
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 20.0
            }, 
            {
                'dttm_forecast': datetime.combine(self.date, time(12, 30)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 40.0
            }, 
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 30.0
            }, 
            {
                'dttm_forecast': datetime.combine(self.date, time(13, 30)), 
                'type': 'L', 'operation_type_id': 8, 
                'value': 10.0
            }, 
            {
                'dttm_forecast': datetime.combine(date, time(13, 0)), 
                'type': 'L', 
                'operation_type_id': 8, 
                'value': 20.0
            }
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(PeriodClients.objects.filter(
            operation_type__work_type__shop_id=13,
            operation_type_id=8
            ).values('dttm_forecast', 'type', 'operation_type_id', 'value').order_by('dttm_forecast')),
            correct_data
        )

    def test_data_not_setted(self):
        self.auth()
        response = self.api_post('/api/demand/set_demand')
        correct_data = {
            'code': 400, 
            'data': {
                'error_type': 'ValueException', 
                'error_message': "[('from_dttm', ['This field is required.']), ('to_dttm', ['This field is required.']), ('shop_id', ['This field is required.'])]"
            }, 
            'info': None
        }
        self.assertEqual(response.json(), correct_data)

class TestGetDemangChangeLogs(TestDemand):

    def setUp(self):
        super().setUp()
        self.dates = []
        test_data = {
            'PeriodDemandChangeLog' : [
                {
                    'dttm_from' : datetime.combine(self.date, time(12, 0)),
                    'dttm_to' : datetime.combine(self.date, time(13, 0)),
                    'operation_type' : self.o_type_5,
                    'multiply_coef' : 0.2
                },
                {
                    'dttm_from' : datetime.combine(self.date, time(15, 0)),
                    'dttm_to' : datetime.combine(self.date, time(18, 0)),
                    'operation_type' : self.o_type_5,
                    'set_value' : 10
                }
            ]
        }
        for model in test_data.keys():
            for data in test_data[model]:
                log = apps.get_model('forecast', model).objects.create(**data)
                self.dates.append(log.dttm_added)

    def test_correct(self):
        self.auth()
        from_dt = Converter.convert_date(self.date)
        to_dt =  Converter.convert_date((self.date + timedelta(days=1)))
        response = self.api_get(
            f'/api/demand/get_demand_change_logs?work_type_id={self.work_type4.id}&from_dt={from_dt}&to_dt={to_dt}&shop_id=2'
        )
        correct_answer = {
            'code': 200,
            'data': [
                {
                    'dttm_added': Converter.convert_datetime(self.dates[0]), 
                    'dttm_from': Converter.convert_datetime(datetime.combine(self.date, time(12, 0))), 
                    'dttm_to': Converter.convert_datetime(datetime.combine(self.date, time(13, 0))), 
                    'work_type_id': self.work_type4.id,
                    'multiply_coef': 0.2, 
                    'set_value': None
                }, 
                {
                    'dttm_added': Converter.convert_datetime(self.dates[1]), 
                    'dttm_from': Converter.convert_datetime(datetime.combine(self.date, time(15, 0))), 
                    'dttm_to': Converter.convert_datetime(datetime.combine(self.date, time(18, 0))), 
                    'work_type_id': self.work_type4.id, 
                    'multiply_coef': None, 
                    'set_value': 10.0
                }
            ],
            'info': None
        }
        self.assertEqual(response.json(), correct_answer)

    def test_data_not_setted(self):
        self.auth()
        response = self.api_get('/api/demand/get_demand_change_logs')
        correct_data = {
            'code': 400, 
            'data': {
                'error_type': 'ValueException', 
                'error_message': "[('work_type_id', ['This field is required.']), ('from_dt', ['This field is required.']), ('to_dt', ['This field is required.']), ('shop_id', ['This field is required.'])]"
            }, 
            'info': None
        }
        self.assertEqual(response.json(), correct_data)

class TestCreatePredBillsRequest(TestDemand):
    
    def setUp(self):
        super().setUp()

    def test_correct(self):
        self.auth()
        data = {
            'shop_id' : 13,
            'dt' : Converter.convert_date(datetime(2018, 7, 7))
        }
        response = self.api_post('/api/demand/create_predbills', data)
        res = response.json()
        self.assertEqual(res['code'], 500)
        self.assertEqual(res['data']['error_type'], 'AlgorithmInternalError')

    def test_data_not_setted(self):
        self.auth()
        response = self.api_post('/api/demand/create_predbills')
        correct_data = {
            'code': 400, 
            'data': {
                'error_type': 'ValueException', 
                'error_message': "[('shop_id', ['This field is required.']), ('dt', ['This field is required.'])]"
            },
            'info': None
        }
        self.assertEqual(response.json(), correct_data)


class TestSetPredBills(TestDemand):

    def setUp(self):
        super().setUp()

    def test_correct(self):
        self.auth()
        data = {
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
        test_data = {
            "shop_id": self.shop.id,
            "access_token": "a", 
            "key": "a", 
            "data": json.dumps(data),
        }

        
        response = self.api_post('/api/demand/set_predbills', test_data)
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
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.first().text, f'Cоставлен новый спрос на период с {Converter.convert_date(datetime(2019, 9, 1))} по {Converter.convert_date(datetime(2019, 11, 2))}')

