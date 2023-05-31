from django.db.models import Q
from drf_yasg.utils import swagger_auto_schema
from rest_framework.pagination import LimitOffsetPagination

from backend.core.shops.service import ShopService
from backend.interfaces.frontend_api.serializers.shops import ShopSerializer
from src.base.models import NetworkConnect, Shop, Region
from src.base.permissions import Permission
from src.base.shop.views import ShopFilter
from src.base.views_abstract import UpdateorCreateViewSet


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
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = ShopSerializer
    filterset_class = ShopFilter
    openapi_tags = ['Shop', ]
    queryset = Shop.objects.all()

    @swagger_auto_schema(responses={200: ShopSerializer(many=True)}, operation_description='GET /rest_api/department/')
    def list(self, request):
        return ShopService.list(self, request)

    @swagger_auto_schema(request_body=ShopSerializer, responses={201: ShopSerializer},
                         operation_description='POST /rest_api/department/')
    def create(self, *args, **kwargs):
        return super().create(*args, **kwargs)

    @swagger_auto_schema(responses={200: ShopSerializer}, operation_description='GET /rest_api/department/{id}/')
    def retrieve(self, *args, **kwargs):
        return super().retrieve(*args, **kwargs)

    @swagger_auto_schema(responses={200: ShopSerializer}, request_body=ShopSerializer,
                         operation_description='PUT /rest_api/department/{id}/')
    def update(self, *args, **kwargs):
        return super().update(*args, **kwargs)

    @swagger_auto_schema(operation_description='DELETE /rest_api/department/{id}/')
    def destroy(self, *args, **kwargs):
        return super().destroy(*args, **kwargs)

    def perform_create(self, serializer):
        ShopService.perform_create(self, serializer)

    def get_queryset(self):
        """
        Возвращает queryset со списком регионов упорядоченных по структуре дерева. Этот queryset
        определяет права доступа к магазинам.
        """
        user = self.request.user
        # only_top = self.request.query_params.get('only_top')
        include_clients = self.request.query_params.get('include_clients')
        include_possible_clients = self.request.query_params.get('include_possible_clients')
        include_outsources = self.request.query_params.get('include_outsources')

        # aa: fixme: refactor code
        # employments = Employment.objects.get_active(
        #     network_id=user.network_id,
        #     user=user).values('shop_id')
        # shops = Shop.objects.filter(id__in=employments.values('shop_id'))
        # if not only_top:
        #     shops = Shop.objects.get_queryset_descendants(shops, include_self=True)
        shops_filter = Q(network_id=user.network_id)
        if include_possible_clients:
            shops_filter |= Q(network_id__in=NetworkConnect.objects.filter(outsourcing_id=user.network_id,
                                                                           allow_choose_shop_from_client_for_employement=True).values_list(
                'client_id', flat=True))
        else:
            if include_clients:
                shops_filter |= Q(
                    network_id__in=NetworkConnect.objects.filter(outsourcing_id=user.network_id).values_list(
                        'client_id', flat=True))
            if include_outsources:
                shops_filter |= Q(network_id__in=NetworkConnect.objects.filter(client_id=user.network_id).values_list(
                    'outsourcing_id', flat=True))

        return super().get_queryset().filter(shops_filter).order_by('level', 'name')

