from rest_framework import viewsets

from src.base.permissions import FilteredListPermission
from src.base.serializers import EmploymentSerializer, UserSerializer
from src.base.filters import EmploymentFilter, UserFilter

from src.base.models import  Employment, User


class EmploymentViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentSerializer
    filterset_class = EmploymentFilter

    queryset = Employment.objects.all()


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = UserSerializer
    filterset_class = UserFilter

    def get_queryset(self):
        shop_id = self.request.query_params.get('shop_id')

        employments = Employment.objects \
            .get_active(shop_id=shop_id)
        return User.objects.filter(id__in=employments.values('user_id'))

