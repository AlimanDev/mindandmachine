from src.util.openapi.descriptions import SHOP_UPDATE, RECIEPT, WORKER_DAY_LIST
from src.util.openapi.integration_serializers import (
    ShopIntegrationSerializer, 
    UserIntegrationSerializer,
    WorkerPositionIntegrationSerializer,
    EmploymentIntegrationSerializer,
    WorkerDayFilterIntegrationSerializer,
    ReceiptIntegrationSerializer,
)
from src.util.openapi.responses import worker_day_list_integration, receipt_integration
from src.base.shop.serializers import ShopSerializer
from src.base.serializers import UserSerializer, WorkerPositionSerializer, EmploymentSerializer

overrides_info = {
    'department': {
        'update': {
            'description': SHOP_UPDATE,
            'id': 'Структура и список подразделений',
            'request_body': ShopIntegrationSerializer(),
            'responses': {
                "200": ShopSerializer,
                "201": ShopSerializer,
            }
        }
    },
    'user': {
        'update': {
            'description': 'Необходимо перенести и поддерживать актуальную информацию по сотрудникам (физическим лицам).',
            'id': 'Информация по Сотрудникам (справочники Сотрудники и ф. л.)',
            'request_body': UserIntegrationSerializer(),
            'responses': {
                "200": UserSerializer,
                "201": UserSerializer,
            }
        }
    },
    'worker_position': {
        'update': {
            'description': 'На основе должности задается базовая ролевая модель для сотрудников.',
            'id': 'Информация по должностям сотрудников',
            'request_body': WorkerPositionIntegrationSerializer(),
            'responses': {
                "200": WorkerPositionSerializer,
                "201": WorkerPositionSerializer,
            }
        }
    },
    'employment': {
        'update': {
            'description': '''Обозначает взаимосвязь между сотрудником (человеком) и подразделением.\n
Уникальность записи идентифицируется по (ID сотрудника, ID подразделения,  Дата начала работы). В произвольный момент времени в одном магазине может быть 1 активная запись по трудоустройству.''',
            'id': 'Информация по Трудоустройству сотрудников (Кадровая История сотрудников интервальный)',
            'request_body': EmploymentIntegrationSerializer(),
            'responses': {
                "200": EmploymentSerializer,
                "201": EmploymentSerializer,
            }
        }
    },
    'worker_day': {
        'list': {
            'description': WORKER_DAY_LIST,
            'id': 'Табель учета рабочего времени',
            'query_serializer': WorkerDayFilterIntegrationSerializer(),
            'responses': worker_day_list_integration,
        }
    },
    'receipt': {
        'update': {
            'description': RECIEPT,
            'id': 'Данные для расчета потребности в персонале',
            'request_body': ReceiptIntegrationSerializer(),
            'responses': receipt_integration,
        }
    }
}
overrides_pk = {
    '/rest_api/user/': 'username',
    '/rest_api/employment/': 'username',
    '/rest_api/receipt/': 'id',
}
