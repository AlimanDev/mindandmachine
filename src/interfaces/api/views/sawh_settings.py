from drf_yasg.utils import swagger_auto_schema
from rest_framework.viewsets import GenericViewSet
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from src.apps.base.models import SAWHSettings
from src.apps.base.permissions import Permission
from src.interfaces.api.serializers.sawhsettings import SAWHSettingsDailySerializer
from src.apps.base.sawhsettings.service import DailySawhCalculatorService


class SAWHSettingsViewSet(GenericViewSet):
    permission_classes = [Permission]
    queryset = SAWHSettings.objects.all()

    @swagger_auto_schema(
        responses={200:'Норма рабочих часов на каждый день'},
        operation_description='Возвращает норму рабочих часов с учётом настроек SAWH за определённый период',
        query_serializer=SAWHSettingsDailySerializer,
    )
    @action(detail=False, methods=['get'], serializer_class=SAWHSettingsDailySerializer)
    def daily(self, request: Request) -> Response:
        """
        GET /rest_api/sawh_settings/daily
        :params
            dt_from: QOS_DATE_FORMAT, required=True
            dt_to: QOS_DATE_FORMAT, required=True
        :return [
            {
                "dt": QOS_DATE_FORMAT,
                "work_types": list[int],
                "worker_position": int,
                "sawh": float
            }
            ...
        ]
        """
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        daily_sawh = DailySawhCalculatorService(**serializer.validated_data).get_daily_sawh()
        return Response(daily_sawh)
