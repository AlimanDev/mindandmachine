from rest_framework.response import Response

from backend.interfaces.frontend_api.serializers.shops import serialize_shop
from src.base.models import Region


class ShopService:
    @staticmethod
    def list(view, request):
        data = list(
            view.filter_queryset(
                view.get_queryset()
            )
        )
        return Response([serialize_shop(s, request) for s in data])  # не

    @staticmethod
    def perform_create(view, serializer):
        serializer.save(region=Region.objects.first())  # TODO: переделать на получение региона по коду в api???
