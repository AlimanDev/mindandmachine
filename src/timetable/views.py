import datetime

from django_filters.rest_framework import FilterSet, BooleanFilter, DjangoFilterBackend
from django_filters import utils
from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication

from src.base.permissions import FilteredListPermission

from src.timetable.models import WorkerDay
from src.timetable.serializers import WorkerDaySerializer, WorkerDayCashboxDetailsSerializer
from src.timetable.filters import MultiShopsFilterBackend, WorkerDayFilter


class WorkerDayViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    permission_name = 'department'
    queryset = WorkerDay.objects.qos_filter_version(1)
    filter_backends = [MultiShopsFilterBackend]
    # filter_backends = [DjangoFilterBackend]

    def list(self, request,  *args, **kwargs):
        queryset = self.get_queryset()#.qos_filter_version(1)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
