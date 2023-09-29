from rest_framework import serializers
from src.interfaces.api.serializers.base import BaseModelSerializer
from src.apps.timetable.models import VacancyBlackList
from django_filters.rest_framework import FilterSet
from src.apps.base.permissions import FilteredListPermission
from src.apps.base.views_abstract import BaseModelViewSet


class VacancyBlackListSerializer(BaseModelSerializer):
    shop_id = serializers.IntegerField()

    class Meta:
        model = VacancyBlackList
        fields = ['id', 'shop_id', 'symbol']


class VacancyBlackListFilter(FilterSet):
    class Meta:
        model = VacancyBlackList
        fields = {
            'shop_id': ['exact', 'in',]
        }


class VacancyBlackListViewSet(BaseModelViewSet):
    serializer_class = VacancyBlackListSerializer
    filterset_class = VacancyBlackListFilter
    queryset = VacancyBlackList.objects.all()
    permission_classes = [FilteredListPermission]
    openapi_tags = ['VacancyBlackList',]
