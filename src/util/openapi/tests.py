from django.test import TestCase
from drf_yasg import openapi

from src.util.openapi.auto_schema import WFMOpenAPISchemaGenerator


class TestOpenAPI(TestCase):
    def test_schema_generation(self):
        info = openapi.Info(
            title="WFM",
            default_version='v1',
            description="Документация REST API для интеграции",
        )
        generator = WFMOpenAPISchemaGenerator(info)
        self.assertIsNotNone(generator.get_schema())

