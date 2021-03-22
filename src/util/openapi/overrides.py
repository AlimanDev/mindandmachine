from src.util.openapi.descriptions import SHOP_UPDATE, USER_UPDATE
from src.util.openapi.integration_serializers import ShopIntegrationSerializer, UserIntegrationSerializer

overrides_info = {
    'department': {
        'update': {
            'description': SHOP_UPDATE,
            'id': 'Структура и список подразделений',
            'request_body': ShopIntegrationSerializer(),
        }
    },
    'user': {
        'update': {
            'description': USER_UPDATE,
            'id': 'Информация по Сотрудникам (справочники Сотрудники и ф. л.)',
            'request_body': UserIntegrationSerializer(),
        }
    }
}
overrides_pk = {
    '/rest_api/department/': 'code',
    '/rest_api/user/': 'username',
}
