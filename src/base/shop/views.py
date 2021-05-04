import datetime

from drf_yasg.utils import swagger_auto_schema

from dateutil.relativedelta import relativedelta
from django.db.models import Q, Sum
from django_filters.rest_framework import NumberFilter, OrderingFilter
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework import serializers

from src.base.filters import BaseActiveNamedModelFilter
from src.base.models import Employment, Shop, Region, NetworkConnect
from src.base.permissions import Permission
from src.base.shop.serializers import ShopSerializer, ShopStatSerializer, serialize_shop
from src.base.shop.utils import get_tree
from src.base.views_abstract import UpdateorCreateViewSet
from src.util.openapi.responses import shop_tree_response_schema_dict as tree_response_schema_dict


class ShopFilter(BaseActiveNamedModelFilter):
    id = NumberFilter(field_name='id', lookup_expr='exact')
    ordering = OrderingFilter(fields=('name', 'code'))

    class Meta:
        model = Shop
        fields = {
            'load_template_id': ['exact'],
            'load_template_status': ['exact'],
        }


class ShopViewSet(UpdateorCreateViewSet):
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

    PUT /rest_api/department/6/, {"title": 'abcd'}
    :return {"id": 6, ...}

    GET /rest_api/department/stat?id=6
    """
    page_size = 10
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = ShopSerializer
    filterset_class = ShopFilter
    openapi_tags = ['Shop',]

    @swagger_auto_schema(responses={200: ShopSerializer(many=True)}, operation_description='GET /rest_api/department/')
    def list(self, request):
        data = list(self.filter_queryset(self.get_queryset()))
        return Response([serialize_shop(s, request) for s in data])

    @swagger_auto_schema(request_body=ShopSerializer, responses={201: ShopSerializer}, operation_description='POST /rest_api/department/')
    def create(self, *args, **kwargs):
        return super().create(*args, **kwargs)

    @swagger_auto_schema(responses={200: ShopSerializer}, operation_description='GET /rest_api/department/{id}/')
    def retrieve(self, *args, **kwargs):
       return super().retrieve(*args, **kwargs)

    @swagger_auto_schema(responses={200: ShopSerializer}, request_body=ShopSerializer, operation_description='PUT /rest_api/department/{id}/')
    def update(self, *args, **kwargs):
        return super().update(*args, **kwargs)

    @swagger_auto_schema(operation_description='DELETE /rest_api/department/{id}/')
    def destroy(self, *args, **kwargs):
       return super().destroy(*args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(region=Region.objects.first())  # TODO: переделать на получение региона по коду в api???

    def get_queryset(self):
        """
        Возвращает queryset со списком регионов упорядоченных по структуре дерева. Этот queryset
        определяет права доступа к магазинам.
        """
        user = self.request.user
        only_top = self.request.query_params.get('only_top')

        # aa: fixme: refactor code
        # employments = Employment.objects.get_active(
        #     network_id=user.network_id,
        #     user=user).values('shop_id')
        # shops = Shop.objects.filter(id__in=employments.values('shop_id'))
        # if not only_top:
        #     shops = Shop.objects.get_queryset_descendants(shops, include_self=True)

        return Shop.objects.filter(network_id=user.network_id).order_by('level', 'name')

    @action(detail=False, methods=['get'], serializer_class=ShopStatSerializer)#, permission_classes=[IsAdminOrIsSelf])
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

    @swagger_auto_schema(responses=tree_response_schema_dict)
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """
        Дерево магазинов в формате для Quasar
        :param request:
        :return:
        """
        user = self.request.user
        only_top = self.request.query_params.get('only_top')

        # aa: fixme: refactor code
        employments = Employment.objects.get_active(
            network_id=user.network_id,
            employee__user=user,
        )

        shops = self.filter_queryset(self.get_queryset())
        shops = shops.filter(id__in=employments.values_list('shop_id', flat=True))
        if not only_top:
            now = datetime.datetime.now()
            shops = Shop.objects.get_queryset_descendants(shops, include_self=True).filter(
                Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=now),
                Q(dt_closed__isnull=True) |
                Q(dt_closed__gte=now.today() - datetime.timedelta(days=30)),
            ).order_by('level', 'name')

        return Response(get_tree(shops))

    @swagger_auto_schema(responses=tree_response_schema_dict)
    @action(detail=False, methods=['get'])
    def outsource_tree(self, request):
        """
        Дерево магазинов клиентов для аутсорсинговой компании в формате для Quasar
        :param request:
        :return:
        """
        user = self.request.user
        clients = NetworkConnect.objects.filter(outsourcing_id=user.network_id).values_list('client_id', flat=True)
        shops = self.filter_queryset(
            Shop.objects.filter(network_id__in=clients).order_by('level', 'name')
        )

        return Response(get_tree(shops))
