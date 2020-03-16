from rest_framework.viewsets import ModelViewSet
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_auth.views import UserDetailsView

from src.base.permissions import FilteredListPermission, Permission
from src.base.serializers import EmploymentSerializer, UserSerializer, FunctionGroupSerializer
from src.base.filters import EmploymentFilter, UserFilter

from src.base.models import  Employment, User, FunctionGroup

from django.utils.timezone import now


class EmploymentViewSet(ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentSerializer
    filterset_class = EmploymentFilter

    queryset = Employment.objects.all()


class UserViewSet(ModelViewSet):
    permission_classes = [Permission]
    serializer_class = UserSerializer
    filterset_class = UserFilter

    queryset = User.objects.all()
    def perform_create(self, serializer):
        serializer.username=now()
        instance=serializer.save()
        instance.username='user_'+ str(instance.id)
        instance.save()


class AuthUserView(UserDetailsView):
    serializer_class = UserSerializer


class FunctionGroupView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FunctionGroupSerializer

    def get_queryset(self):
        user = self.request.user

        groups = Employment.objects \
            .get_active(user=user).values_list("function_group_id", flat=True)
        return FunctionGroup.objects.filter(group__in=groups).distinct('func')
