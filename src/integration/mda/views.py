import io
import json

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from .integration import MdaIntegrationHelper


class IntegrationDataExportView(APIView):
    parser_classes = ()

    def get(self, *args, **kwargs):
        if not self.request.user.is_superuser:
            raise PermissionDenied()

        mda_integration_helper = MdaIntegrationHelper()
        format = self.request.query_params.get('output_format', 'xlsx')
        threshold_seconds = self.request.query_params.get('threshold_seconds', None)
        if threshold_seconds:
            threshold_seconds = int(threshold_seconds)
        if format == 'xlsx':
            output = io.BytesIO()
            mda_integration_helper.export_data(
                threshold_seconds=threshold_seconds, plain_shops=True, output=output)
            output.seek(0)
            response = HttpResponse(
                output,
                content_type='application/octet-stream',
            )
        elif format == 'json':
            data = {
                'users': mda_integration_helper._get_users_data(threshold_seconds=threshold_seconds),
                'orgstruct': mda_integration_helper._get_orgstruct_data(threshold_seconds=threshold_seconds),
            }
            response = HttpResponse(
                json.dumps(data),
                content_type='application/json',
            )
        else:
            raise ValidationError('invalid format')

        response[
            'Content-Disposition'] = f'attachment; filename="mda_integration_data_{timezone.now().date()}.{format}"'
        return response
