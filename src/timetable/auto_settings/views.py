from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from src.base.permissions import Permission
from src.timetable.auto_settings.serializers import (
    AutoSettingsCreateSerializer,
    AutoSettingsDeleteSerializer,
    AutoSettingsSetSerializer,
)
from .autosettings import AutoSettings


class AutoSettingsViewSet(viewsets.ViewSet):
    serializer_class = AutoSettingsCreateSerializer
    permission_classes = [Permission]
    basename = 'AutoSettings'
    openapi_tags = ['AutoSettings',]

    @swagger_auto_schema(methods=['post'], request_body=AutoSettingsCreateSerializer, responses={200:'Empty response', 400: 'Fail sending data to server.'})
    @action(detail=False, methods=['post'])
    def create_timetable(self, request):
        """
        Собирает данные в нужном формате и отправляет запрос на составления на алгоритмы.
        Args:
            shop_id, dt_from, dt_to, is_remarking            
        """

        serializer = AutoSettingsCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AutoSettings(request.user.network).create_timetable(serializer.validated_data)
        return Response()


    @swagger_auto_schema(request_body=AutoSettingsSetSerializer, methods=['post'], responses={200: '{}', 400: 'cannot parse json'})
    @action(detail=False, methods=['post'])
    def set_timetable(self, request):
        """
        Ждет request'a от qos_algo. Когда получает, записывает данные по расписанию в бд

        Args:
            method: POST
            url: /rest_api/auto_settings/set_timetable/
            data(str): json data с данными от qos_algo

        Raises:
            JsonResponse.does_not_exists_error: если расписания нет в бд

        Note:
            Отправляет уведомление о том, что расписание успешно было создано
        """

        stats = AutoSettings(request.user.network).set_timetable(request.data)
        return Response({'stats': stats})


    @swagger_auto_schema(request_body=AutoSettingsDeleteSerializer, methods=['post'], responses={200: 'empty response'})
    @action(detail=False, methods=['post'])
    def delete_timetable(self, request):
        """
        Удаляет расписание на заданный месяц. Также отправляет request на qos_algo на остановку задачи в селери

        Args:
            method: POST
            url: /api/timetable/auto_settings/delete_timetable
            shop_id(int): required = True
            dt(QOS_DATE): required = True

        Note:
            Отправляет уведомление о том, что расписание было удалено
        """

        serializer = AutoSettingsDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deleted, _ = AutoSettings(request.user.network).delete_timetable(serializer.validated_data)
        return Response({'deleted': deleted})


