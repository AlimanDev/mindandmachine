import datetime
from dateutil.relativedelta import relativedelta

from django.db.models import Q, Sum
from django_filters.rest_framework import FilterSet

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from src.base.models import Employment, Shop

from src.base.shop.serializers import ShopSerializer, ShopStatSerializer


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

    PUT /rest_api/department/6/, {"title": 'abcd'}
    :return {"id": 6, ...}

    GET /rest_api/department/stat?id=6
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ShopSerializer
    filterset_class = ShopFilter

    def get_object(self):
        if self.request.method == 'GET':
            by_code = self.request.query_params.get('by_code', False)
        else:
            by_code = self.request.data.get('by_code', False)
        if by_code:
            self.lookup_field = 'code'
            self.kwargs['code'] = self.kwargs['pk']
        return super().get_object()

    def get_queryset(self):
        """
        Возвращает queryset со списком регионов упорядоченных по структуре дерева. Этот queryset
        определяет права доступа к магазинам.
        """
        user = self.request.user
        only_top = self.request.query_params.get('only_top')

        employments = Employment.objects.get_active(
            network_id=user.network_id,
            user=user).values('shop_id')
        shops = Shop.objects.filter(id__in=employments.values('shop_id'))
        if not only_top:
            return Shop.objects.get_queryset_descendants(shops, include_self=True).filter(
                network_id=user.network_id,
            )
        else:
            return shops

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

    def list(self, request):
        """
        Дерево магазинов в формате для Quasar
        :param request:
        :return:
        """

        shops = self.filter_queryset(self.get_queryset())
        tree = []
        ids = []
        elems = []
        for shop in shops:
            parent_id = shop.parent_id
            if parent_id in ids:
                for i, elem in enumerate(elems):
                    if elem['id'] == parent_id:
                        ids = ids[0:i+1]
                        elems = elems[0:i+1]
                        child_list = elem["children"]
            else:
                ids = []
                elems = []
                child_list = tree

            child_list.append({
                "id": shop.id,
                "label": shop.name,
                "tm_shop_opens":shop.tm_shop_opens,
                "tm_shop_closes":shop.tm_shop_closes,
                "forecast_step_minutes":shop.forecast_step_minutes,
                "children": []
            })

            elems.append(child_list[-1])
            ids.append(shop.id)

        return Response(tree)
