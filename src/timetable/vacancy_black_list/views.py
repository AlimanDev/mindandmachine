from rest_framework import serializers, viewsets
from src.timetable.models import VacancyBlackList
from django_filters.rest_framework import FilterSet, NumberFilter
from src.base.permissions import FilteredListPermission


class VacancyBlackListSerializer(serializers.ModelSerializer):
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


class VacancyBlackListViewSet(viewsets.ModelViewSet):
    serializer_class = VacancyBlackListSerializer
    filterset_class = VacancyBlackListFilter
    queryset = VacancyBlackList.objects.all()
    permission_classes = [FilteredListPermission]