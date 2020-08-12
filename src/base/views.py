from django.utils.timezone import now
from django.db.models import F
from django.db.models.functions import Coalesce
from rest_auth.views import UserDetailsView

from rest_framework import mixins
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.decorators import action

from src.base.permissions import Permission
from src.base.serializers import (
    EmploymentSerializer,
    UserSerializer, 
    FunctionGroupSerializer, 
    WorkerPositionSerializer, 
    NotificationSerializer, 
    SubscribeSerializer, 
    PasswordSerializer, 
    ShopSettingsSerializer, 
    NetworkSerializer, 
    AuthUserSerializer,
    EmploymentListSerializer,
    UserListSerializer,
)
from src.base.filters import NotificationFilter, SubscribeFilter, EmploymentFilter
from src.base.models import (
    Employment,
    FunctionGroup,
    Network,
    Notification,
    Subscribe,
    ShopSettings,
    WorkerPosition,
    User,
)

from src.base.filters import UserFilter


class EmploymentViewSet(ModelViewSet):
    """
        обязательные поля при редактировании PUT:
            position_id
            dt_hired
            dt_fired
        при создании POST дополнительно еще:
            shop_id
            user_id
        Если дата увольнения не задана, надо передать пустое поле.
    """
    permission_classes = [Permission]
    serializer_class = EmploymentSerializer
    filterset_class = EmploymentFilter

    def get_object(self):
        if self.request.method == 'GET':
            by_code = self.request.query_params.get('by_code', False)
        else:
            by_code = self.request.data.get('by_code', False)
        if by_code:
            self.lookup_field = 'tabel_code'
            self.kwargs['tabel_code'] = self.kwargs['pk']
        return super().get_object()

    def get_queryset(self):
        return Employment.objects.filter(
            shop__network_id=self.request.user.network_id
        )


    def get_serializer_class(self):
        if self.action == 'list':
            return EmploymentListSerializer
        else:
            return EmploymentSerializer


class UserViewSet(ModelViewSet):
    page_size = 10
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = UserSerializer
    filterset_class = UserFilter

    def get_object(self):
        if self.request.method == 'GET':
            by_code = self.request.query_params.get('by_code', False)
        else:
            by_code = self.request.data.get('by_code', False)
        if by_code:
            self.lookup_field = 'username'
            self.kwargs['username'] = self.kwargs['pk']
        return super().get_object()

    def get_queryset(self):
        user = self.request.user
        return User.objects.filter(
            network_id=user.network_id
        )

    def perform_create(self, serializer):
        if 'username' not in serializer.validated_data:
            instance = serializer.save(username = now())
            instance.username = 'user_' + str(instance.id)
            instance.save()
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        user = self.get_object()
        serializer = PasswordSerializer(data=request.data, instance=user, context={'request':request})

        if serializer.is_valid():
            serializer.save()
            return Response()
        else:
            return Response(serializer.errors,
                            status=HTTP_400_BAD_REQUEST)


    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        else:
            return UserSerializer


class AuthUserView(UserDetailsView):
    serializer_class = AuthUserSerializer


class FunctionGroupView(ModelViewSet):
    permission_classes = [Permission]
    serializer_class = FunctionGroupSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        user = self.request.user

        groups = Employment.objects.get_active(
            network_id=user.network_id,
            user=user).annotate(
            group_id=Coalesce(F('function_group_id'),F('position__group_id'))
        ).values_list("group_id", flat=True)
        return FunctionGroup.objects.filter(group__in=groups).distinct('func')


class WorkerPositionViewSet(ModelViewSet):
    permission_classes = [Permission]
    serializer_class = WorkerPositionSerializer
    pagination_class = LimitOffsetPagination

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
        return WorkerPosition.objects.filter(
            dttm_deleted__isnull=True,
            network_id=self.request.user.network_id
        )


class SubscribeViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscribeSerializer
    filterset_class = SubscribeFilter

    def get_queryset(self):
        user = self.request.user
        return Subscribe.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class NotificationViewSet(
                   mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin,
                   mixins.ListModelMixin,
                   GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter

    def get_queryset(self):
        user = self.request.user
        return Notification.objects.filter(worker=user).select_related('event', 'event__worker_day_details', 'event__shop')


class ShopSettingsViewSet(ModelViewSet):
    page_size = 10
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = ShopSettingsSerializer

    def get_queryset(self):
        user = self.request.user
        return ShopSettings.objects.filter(
            network_id=user.network_id
        )


class NetworkViewSet(ModelViewSet):
    permission_classes = [Permission]
    serializer_class = NetworkSerializer
    queryset = Network.objects.all()

