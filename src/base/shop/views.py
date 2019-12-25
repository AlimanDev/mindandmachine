from src.base.models import Shop, Employment
from rest_framework import serializers, viewsets
from django.utils import six
from timezone_field import TimeZoneField as TimeZoneField_
from src.base.permissions import Permission


class TimeZoneField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(TimeZoneField_.CHOICES + [(None, "")], **kwargs)

    def to_representation(self, value):
        return six.text_type(super().to_representation(value))


# Serializers define the API representation.
class ShopSerializer(serializers.HyperlinkedModelSerializer):
    parent_id = serializers.IntegerField(required=False)
    timezone = TimeZoneField()
    class Meta:
        model = Shop
        fields = ['id', 'parent_id', 'title', 'tm_shop_opens', 'tm_shop_closes', 'code',
                  'address', 'type', 'dt_opened', 'dt_closed', 'timezone']



class ShopViewSet(viewsets.ModelViewSet):
    permission_classes = [Permission]
    serializer_class = ShopSerializer
    def get_queryset(self):
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

