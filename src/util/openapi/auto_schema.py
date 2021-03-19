from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.openapi import Parameter
from django.test import override_settings
from src.conf.djconfig import OPENAPI_INTEGRATION_MODELS_METHODS
from src.util.openapi.overrides import overrides_info


class WFMAutoSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        tags = self.overrides.get('tags', None) or getattr(self.view, 'openapi_tags', [])
        if not tags:
            tags = [operation_keys[0]]

        return tags


class WFMAutoSchemaIntegration(WFMAutoSchema):
    def __init__(self, view, path, method, components, request, overrides, operation_keys=None):
        if tuple(operation_keys[1:3]) in OPENAPI_INTEGRATION_MODELS_METHODS:
            path = overrides_info.get(operation_keys[1], {}).get(operation_keys[2], {}).get('path', path)
        super(WFMAutoSchemaIntegration, self).__init__(view, path, method, components, request, overrides)
    def get_operation(self, operation_keys=None):
        if not tuple(operation_keys[1:3]) in OPENAPI_INTEGRATION_MODELS_METHODS:
            return None
        else:
            self.overrides['request_body'] = overrides_info.get(operation_keys[1], {}).get(operation_keys[2], {}).get('request_body', self.get_request_serializer())
            self.overrides['manual_parameters'] = [Parameter('code', 'path', required=True, type='string'),]
            operation = super().get_operation(operation_keys=operation_keys)
            operation.tags = ['Integration',]
            operation.description = overrides_info.get(operation_keys[1], {}).get(operation_keys[2], {}).get('description', operation.description)
            operation.operation_id = overrides_info.get(operation_keys[1], {}).get(operation_keys[2], {}).get('id', operation.operation_id)
            return operation


class WFMOpenAPISchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        """Generate a :class:`.Swagger` object with custom tags"""

        swagger = super().get_schema(request, public)
        swagger.tags = [
            {
                "name": "api",
                "description": "everything about your API"
            },
            {
                "name": "rest_api",
                "description": "everything about your REST API"
            },
            {
                "name": "User",
                "description": "everything about your users"
            },
        ]

        return swagger


class WFMIntegrationAPISchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        """Generate a :class:`.Swagger` object with custom tags"""
        SWAGGER_SETTINGS = {
            'TAGS_SORTER': 'alpha',
            'OPERATIONS_SORTER': 'alpha',
            'DEFAULT_AUTO_SCHEMA_CLASS': "src.util.openapi.auto_schema.WFMAutoSchemaIntegration",
        }
        with override_settings(SWAGGER_SETTINGS=SWAGGER_SETTINGS):
            swagger = super().get_schema(request, public)
            swagger.tags = [
                {
                    "name": "Integration",
                    "description": """# Общая информация
                    Для минимизации ручного ввода данных в рамках внедрения WFM-решения Mind&Machine предполагается интеграция с системами клиента для обмена следующими потоками данных:\n
1. Структура и список подразделений
2. Список сотрудников
3. Список должностей
4. Список трудоустройств сотрудников
5. Табель учета рабочего времени
Для обмена используется REST API WFM-решения, формат для передачи данных – JSON.\n
Запросы необходимо отправлять на: *.mindandmachine.ru\n
Для получения данных используются GET-запросы.\n
Для создания или изменения данных используются PUT-запросы.\n
При успешном выполнении запроса возвращается статус 200. Если при вызове PUT-запроса создается объект, то возвращается статус 201.\n
                    """
                },
            ]

            return swagger