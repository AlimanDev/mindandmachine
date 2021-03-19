from src.util.openapi.descriptions import SHOP_UPDATE
from src.util.openapi.integration_serializers import ShopIntegrationSerializer

overrides_info = {
    'department': {
        'update': {
            'description': SHOP_UPDATE,
            'id': 'Структура и список подразделений',
            'request_body': ShopIntegrationSerializer(),
            'path': '/rest_api/department/{code}/'
        }
    }
}
