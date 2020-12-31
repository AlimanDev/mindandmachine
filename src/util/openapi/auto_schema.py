from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg.generators import OpenAPISchemaGenerator


class WFMAutoSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        tags = self.overrides.get('tags', None) or getattr(self.view, 'openapi_tags', [])
        if not tags:
            tags = [operation_keys[0]]

        return tags


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
