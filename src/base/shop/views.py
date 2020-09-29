import datetime
from dateutil.relativedelta import relativedelta

from django.db.models import Q, Sum
from django_filters.rest_framework import FilterSet

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination

from src.base.models import Employment, Shop
from src.base.permissions import Permission

from src.base.shop.serializers import ShopSerializer, ShopStatSerializer
from src.base.views import BaseActiveNamedModelViewSet


class ShopFilter(FilterSet):
    class Meta:
        model = Shop
        fields = {
            'id':['exact', 'in'],
            'code': ['exact', 'in'],
            'load_template_id': ['exact',],
            'load_template_status': ['exact'],
        }


class ShopViewSet(BaseActiveNamedModelViewSet):
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
            user=user).values('shop_id')

        shops = self.filter_queryset(self.get_queryset())
        level = 0
        shops = shops.filter(id__in=employments.values('shop_id'))
        if not only_top:
            shops = Shop.objects.get_queryset_descendants(shops, include_self=True)

        tree = []
        parent_indexes = {}
        for shop in shops:
            if not shop.parent_id in parent_indexes:
                tree.append({
                    "id": shop.id,
                    "label": shop.name,
                    "tm_open_dict": shop.open_times,
                    "tm_close_dict" :shop.close_times,
                    "address": shop.address,
                    "forecast_step_minutes":shop.forecast_step_minutes,
                    "children": []
                })
                parent_indexes[shop.id] = [len(tree) - 1,]
            else:
                root = tree[parent_indexes[shop.parent_id][0]]
                parent = root
                for i in parent_indexes[shop.parent_id][1:]:
                    parent = parent['children'][i]
                parent['children'].append({
                    "id": shop.id,
                    "label": shop.name,
                    "tm_open_dict": shop.open_times,
                    "tm_close_dict" :shop.close_times,
                    "address": shop.address,
                    "forecast_step_minutes":shop.forecast_step_minutes,
                    "children": []
                })
                parent_indexes[shop.id] = parent_indexes[shop.parent_id].copy()
                parent_indexes[shop.id].append(len(parent['children']) - 1)
        # tree = []
        # ids = []
        # elems = []
        # for shop in shops:
        #     parent_id = shop.parent_id
        #     if parent_id in ids:
        #         for i, elem in enumerate(elems):
        #             if elem['id'] == parent_id:
        #                 ids = ids[0:i+1]
        #                 elems = elems[0:i+1]
        #                 child_list = elem["children"]
        #     else:
        #         ids = []
        #         elems = []
        #         child_list = tree

        #     child_list.append({
        #         "id": shop.id,
        #         "label": shop.name,
        #         "tm_open_dict": shop.open_times,
        #         "tm_close_dict" :shop.close_times,
        #         "address": shop.address,
        #         "forecast_step_minutes":shop.forecast_step_minutes,
        #         "children": []
        #     })

        #     elems.append(child_list[-1])
        #     ids.append(shop.id)

        return Response(tree)
