from rest_framework import viewsets

from src.base.permissions import FilteredListPermission, Permission
from src.base.serializers import EmploymentSerializer, UserSerializer
from src.base.filters import EmploymentFilter, UserFilter

from src.base.models import  Employment, User


class EmploymentViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentSerializer
    filterset_class = EmploymentFilter

    queryset = Employment.objects.all()


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [Permission]
    serializer_class = UserSerializer
    filterset_class = UserFilter

    queryset = User.objects.all()
