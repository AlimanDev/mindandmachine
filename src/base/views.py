from django.utils import timezone
from django.db.models import F, Q
from django.db.models.functions import Coalesce
from rest_auth.views import UserDetailsView

from rest_framework import mixins
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework import status
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
    GroupSerializer,
    AutoTimetableSerializer,
    BreakSerializer,
)
from src.base.filters import NotificationFilter, SubscribeFilter, EmploymentFilter, BaseActiveNamedModelFilter
from src.base.models import (
    Employment,
    FunctionGroup,
    Network,
    Notification,
    Subscribe,
    ShopSettings,
    WorkerPosition,
    User,
    Group,
    Break,
)

from src.base.filters import UserFilter
from src.base.views_abstract import (
    BaseActiveNamedModelViewSet,
    UpdateorCreateViewSet
)
from django.middleware.csrf import rotate_token


class EmploymentViewSet(UpdateorCreateViewSet):
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

    def perform_create(self, serializer):
        serializer.save(network=self.request.user.network)

    def get_queryset(self):
        return Employment.objects.filter(
            shop__network_id=self.request.user.network_id
        ).order_by('-dt_hired')

    def get_serializer_class(self):
        if self.action == 'list':
            return EmploymentListSerializer
        else:
            return EmploymentSerializer

    @action(detail=False, methods=['post',])
    def auto_timetable(self, request):
        data = AutoTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        Employment.objects.filter(id__in=data.get('employment_ids')).update(auto_timetable=data.get('auto_timetable'))
        return Response()


class UserViewSet(BaseActiveNamedModelViewSet):
    page_size = 10
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = UserSerializer
    filterset_class = UserFilter
    get_object_field = 'username'

    def get_queryset(self):
        user = self.request.user
        return User.objects.filter(
            network_id=user.network_id
        )

    def perform_create(self, serializer):
        if 'username' not in serializer.validated_data:
            instance = serializer.save(username = timezone.now())
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        else:
            return UserSerializer


class AuthUserView(UserDetailsView):
    serializer_class = AuthUserSerializer

    def check_permissions(self, request, *args, **kwargs):
        rotate_token(request)
        return super().check_permissions(request, *args, **kwargs)


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


    @action(detail=False, methods=['get'])
    def functions(self, request):
        return Response(FunctionGroup.FUNCS)


class WorkerPositionViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = WorkerPositionSerializer
    pagination_class = LimitOffsetPagination
    filterset_class = BaseActiveNamedModelFilter

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


class ShopSettingsViewSet(BaseActiveNamedModelViewSet):
    page_size = 10
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = ShopSettingsSerializer
    filterset_class = BaseActiveNamedModelFilter

    def get_queryset(self):
        user = self.request.user
        return ShopSettings.objects.filter(
            network_id=user.network_id
        )


class NetworkViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = NetworkSerializer
    queryset = Network.objects.all()


class GroupViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = GroupSerializer
    pagination_class = LimitOffsetPagination
    filterset_class = BaseActiveNamedModelFilter
    
    def get_queryset(self):
        return Group.objects.filter(
            network_id=self.request.user.network_id,
        )


class BreakViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = BreakSerializer
    filterset_class = BaseActiveNamedModelFilter

    def get_queryset(self):
        return Break.objects.filter(
            network_id=self.request.user.network_id,
        )
