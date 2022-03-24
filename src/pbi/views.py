from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import (
    PermissionDenied,
    APIException,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ReportPermission,
)
from .services.pbiembedservice import PbiEmbedService


class GetEmbedInfoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        report_permission = ReportPermission.get_report_perm(user=request.user)

        if not report_permission:
            raise PermissionDenied(_('There are no reports available.'))

        try:
            embed_info = PbiEmbedService(
                report_config=report_permission.report,
                user_id=request.user.id if report_permission.report.use_rls else None,
            ).get_embed_params_for_single_report()
            return Response(embed_info)
        except Exception as ex:
            raise APIException(str(ex))
