from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg import openapi
from django.test import override_settings
from src.conf.djconfig import OPENAPI_INTEGRATION_MODELS_METHODS
from src.util.openapi.overrides import overrides_info, overrides_pk


class WFMAutoSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        tags = self.overrides.get('tags', None) or getattr(self.view, 'openapi_tags', [])
        if not tags:
            tags = [operation_keys[0]]

        return tags


class WFMAutoSchemaIntegration(WFMAutoSchema):
    def get_operation(self, operation_keys=None):
        if not tuple(operation_keys[1:3]) in OPENAPI_INTEGRATION_MODELS_METHODS:
            return None
        else:
            self.overrides['request_body'] = overrides_info.get(operation_keys[1], {}).get(operation_keys[2], {}).get('request_body', self.get_request_serializer())
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

    def get_path_parameters(self, path, view_cls):
        parameters = super().get_path_parameters(path, view_cls)
        for p in parameters:
            if p.in_ == openapi.IN_PATH and p.type == openapi.TYPE_STRING:
                p.type = openapi.TYPE_STRING
        return parameters

    def coerce_path(self, path, view):
        """Coerce {pk} path arguments into the name of the model field, where possible. This is cleaner for an
        external representation (i.e. "this is an identifier", not "this is a database primary key").

        :param str path: the path
        :param rest_framework.views.APIView view: associated view
        :rtype: str
        """
        if '{pk}' not in path:
            return path
        
        return path.replace('{pk}', '{%s}' % overrides_pk.get(path.replace('{pk}/', ''),'code'))
