import datetime
from dateutil.relativedelta import relativedelta
from timezone_field import TimeZoneField as TimeZoneField_

from django.db.models import Q, Sum
from django.utils import six
from django_filters.rest_framework import FilterSet

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from src.base.permissions import Permission
from src.base.models import  Employment, Shop


class TimeZoneField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(TimeZoneField_.CHOICES + [(None, "")], **kwargs)

    def to_representation(self, value):
        return six.text_type(super().to_representation(value))


# Serializers define the API representation.
class ShopSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(required=False)
    region_id = serializers.IntegerField(required=False)
    timezone = TimeZoneField()
    class Meta:
        model = Shop
        fields = ['id', 'parent_id', 'name', 'tm_shop_opens', 'tm_shop_closes', 'code',
                  'address', 'type', 'dt_opened', 'dt_closed', 'timezone','break_triplets', 'region_id']

class ShopStatSerializer(serializers.Serializer):
    id=serializers.IntegerField()
    parent_id=serializers.IntegerField()
    name=serializers.CharField()
    fot_curr=serializers.FloatField()
    fot_prev=serializers.FloatField()
    revenue_prev=serializers.FloatField()
    revenue_curr=serializers.FloatField()
    lack_prev=serializers.FloatField()
    lack_curr=serializers.FloatField()


class ShopFilter(FilterSet):
    class Meta:
        model = Shop
        fields = {
            'id':['exact', 'in'],
        }


class ShopViewSet(viewsets.ModelViewSet):
    """
    GET /rest_api/department/?id__in=6,7
    :return [{"id":6, ...},{"id":7, ...}]

    GET /rest_api/department/
    :return [   {"id": 1}
        {"id":6, parent_id: 1},
        {"id":61, parent_id: 6},
        {"id":7, parent_id: 1}
    ]

    GET /rest_api/department/6/
    :return [   {"id": 6, ...}
    ]


    POST /rest_api/department/, {"title": 'abcd'}
    :return {"id": 10, ...}

    PUT /rest_api/department/6, {"title": 'abcd'}
    :return {"id": 6, ...}

    GET /rest_api/department/stat?id=6
    """
    permission_classes = [Permission]
    serializer_class = ShopSerializer
    filterset_class = ShopFilter

    def get_queryset(self):
        """
        Возвращает queryset со списком регионов упорядоченных по структуре дерева. Этот queryset
        определяет права доступа к магазинам.
        """
        user = self.request.user
        only_top = self.request.query_params.get('only_top')

        employments = Employment.objects \
            .get_active(user=user).values('shop_id')
        shops = Shop.objects.filter(id__in=employments.values('shop_id'))
        if not only_top:
            return Shop.objects.get_queryset_descendants(shops, include_self=True)
        else:
            return shops

        # funcs = FunctionGroup.objects.filter(func='department', group__employment__in=employments)
        #
        # for employment in employments:
        #     # res=employment.shop.get_ancestor_by_level_distance(employment.function_group.level_up).get_descendants(employment.function_group.level_up)
        #     res=employment.shop.get_descendants(include_self=True)
        #     shops.append(list(res))
        # return shops
        # function_groups = FunctionGroup.objects.all
        # queryset = Shop.objects.

    @action(detail=False, methods=['get']) #, permission_classes=[IsAdminOrIsSelf])
    def stat(self, request):
        """
        Статистика для магазина, или списка магазинов, заданных фильтром ShopFilter
        права доступа - 'Shop_stat' в FunctionGroup
        :return: [{
            'id': 12,
            'parent_id': 1,
            'title': 'Shop1',
            'fot_curr': 10.0,
            'fot_prev': 5.0,
            'revenue_prev': 5.0,
            'revenue_curr': 10.0,
            'lack_prev': 5.0,
            'lack_curr': 10.0}]
        """
        dt_curr = datetime.datetime.today().replace(day=1)
        dt_prev = dt_curr - relativedelta(months=1)

        shops = self.filter_queryset(
            self.get_queryset()
        ).annotate(
            fot_prev=Sum('timetable__fot', filter=Q(timetable__dt=dt_prev)),
            fot_curr=Sum('timetable__fot', filter=Q(timetable__dt=dt_curr)),
            revenue_prev=Sum('timetable__fot_revenue', filter=Q(timetable__dt=dt_prev)),
            revenue_curr=Sum('timetable__fot_revenue', filter=Q(timetable__dt=dt_curr)),
            lack_prev=Sum('timetable__lack', filter=Q(timetable__dt=dt_prev)),
            lack_curr=Sum('timetable__lack', filter=Q(timetable__dt=dt_curr)),
        )
        serializer = ShopStatSerializer(shops, many=True)
        return Response(serializer.data)
