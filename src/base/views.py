from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.db.models.query import Prefetch
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_yasg.utils import swagger_auto_schema
from requests.exceptions import HTTPError
from rest_auth.views import UserDetailsView
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from src.base.filters import (
    NotificationFilter,
    SubscribeFilter,
    EmploymentFilter,
    BaseActiveNamedModelFilter,
    ShopScheduleFilter,
)
from src.base.filters import UserFilter, EmployeeFilter
from src.base.models import (
    Employment,
    FunctionGroup,
    Network,
    NetworkConnect,
    Notification,
    Subscribe,
    ShopSettings,
    WorkerPosition,
    User,
    Group,
    Break,
    ShopSchedule,
    Employee,
)
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
    ShopScheduleSerializer,
    EmployeeSerializer,
)
from src.base.views_abstract import (
    BaseActiveNamedModelViewSet,
    UpdateorCreateViewSet,
    BaseModelViewSet,
)
from src.recognition.api.recognition import Recognition
from src.recognition.models import UserConnecter
from src.timetable.worker_day.tasks import recalc_wdays
from .filter_backends import EmployeeFilterBackend


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
    openapi_tags = ['Employment', 'Integration',]

    def perform_update(self, serializer):
        serializer.save(dttm_deleted=None)

    def get_queryset(self):
        manager = Employment.objects
        if self.action in ['update']:
            manager = Employment.objects_with_excluded

        qs = manager.filter(
            Q(shop__network_id=self.request.user.network_id) | 
            Q(employee__user__network_id=self.request.user.network_id), # чтобы можно было аутсорсу редактировать трудоустройтсва своих сотрудников
        ).order_by('-dt_hired')
        if self.action in ['list', 'retrieve']:
            qs = qs.select_related('employee', 'employee__user', 'shop').prefetch_related('work_types', 'worker_constraints')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return EmploymentListSerializer
        else:
            return EmploymentSerializer

    @swagger_auto_schema(responses={200:'OK'},request_body=AutoTimetableSerializer)
    @action(detail=False, methods=['post',], serializer_class=AutoTimetableSerializer)
    def auto_timetable(self, request):
        data = AutoTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        Employment.objects.filter(id__in=data.get('employment_ids')).update(auto_timetable=data.get('auto_timetable'))
        return Response()


    @action(detail=True, methods=['put',])
    def timetable(self, request, pk=None):
        data = EmploymentSerializer(data=request.data, instance=self.get_object(), context={'request':request, 'view': self})
        data.is_valid(raise_exception=True)
        data.save()
        return Response(data.data)


class UserViewSet(UpdateorCreateViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = UserSerializer
    filterset_class = UserFilter
    get_object_field = 'username'
    openapi_tags = ['User', 'Integration',]

    def get_queryset(self):
        user = self.request.user
        allowed_networks = list(NetworkConnect.objects.filter(
            Q(allow_assign_employements_from_outsource=True) | 
            Q(allow_choose_shop_from_client_for_employement=True),
            client_id=user.network_id,
        ).values_list('outsourcing_id', flat=True)) + [user.network_id]
        return User.objects.filter(
            network_id__in=allowed_networks,
        ).annotate(
            userconnecter_id=F('userconnecter'),
        ).distinct()

    def perform_create(self, serializer):
        if 'username' not in serializer.validated_data:
            instance = serializer.save(username=timezone.now())
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

    @action(detail=True, methods=['post'], parser_classes=(MultiPartParser,))
    def add_biometrics(self, *args, **kwargs):
        user = self.get_object()

        try:
            user.userconnecter
        except UserConnecter.DoesNotExist:
            if 'file' not in self.request.data:
                return Response({"detail": _('It is necessary to transfer a biometrics template (file field).')}, 400)
            biometrics_image = self.request.data['file']
            recognition = Recognition()
            try:
                partner_id = recognition.create_person({"id": user.id})
                recognition.upload_photo(partner_id, biometrics_image)
            except HTTPError as e:
                return Response({"detail": str(e)}, e.response.status_code)

            UserConnecter.objects.create(
                user=user,
                partner_id=partner_id,
            )
            user.avatar = biometrics_image
            user.save()
            success_msg = _('Biometrics template added successfully.')
            return Response({"detail": success_msg}, status=status.HTTP_200_OK)
        else:
            error_msg = _("The employee has biometrics. "
                          "To add a new biometrics template, you need to delete the current template.")
            return Response({"detail": error_msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def delete_biometrics(self, request, pk=None):
        user = self.get_object()
        
        try:
            user.userconnecter
        except:
            return Response({"detail": "У сотрудника нет биометрии"}, status=status.HTTP_400_BAD_REQUEST)

        recognition = Recognition()
        recognition.delete_person(user.userconnecter.partner_id)
        UserConnecter.objects.filter(user_id=user.id).delete()
        user.avatar = None
        user.save()
            
        return Response({"detail": "Биометрия сотрудника успешно удалена"}, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        else:
            return UserSerializer


class EmployeeViewSet(UpdateorCreateViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = EmployeeSerializer
    filterset_class = EmployeeFilter
    filter_backends = [EmployeeFilterBackend]
    openapi_tags = ['Employee', ]

    def get_queryset(self):
        network_filter = Q(user__network_id=self.request.user.network_id)
        # сотрудники из аутсорс сети только для чтения
        if self.action in ['list', 'retrieve']:
            network_filter |= Q(
                user__network_id__in=NetworkConnect.objects.filter(
                    client_id=self.request.user.network_id, 
                    allow_assign_employements_from_outsource=True,
                ).values_list('outsourcing_id', flat=True)
            )

        qs = Employee.objects.filter(
            network_filter,
        ).select_related(
            'user',
        )

        if self.request.query_params.get('include_employments'):
            queryset = Employment.objects.all()
            if self.request.query_params.get('shop_network__in'):
                queryset = queryset.filter(shop__network_id__in=self.request.query_params.get('shop_network__in').split(','))
            if self.request.query_params.get('show_constraints'):
                queryset = queryset.prefetch_related('worker_constraints')
            qs = qs.prefetch_related(Prefetch('employments', queryset=queryset))

        return qs.distinct()


class AuthUserView(UserDetailsView):
    serializer_class = AuthUserSerializer
    openapi_tags = ['Auth',]

    def check_permissions(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            rotate_token(request)
        return super().check_permissions(request, *args, **kwargs)

    def get_queryset(self):
        return User.objects.select_related('network').prefetch_related('network__outsourcings', 'network__clients').all()


class FunctionGroupView(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = FunctionGroupSerializer
    pagination_class = LimitOffsetPagination
    openapi_tags = ['FunctionGroup',]

    def get_queryset(self):
        user = self.request.user

        groups = Employment.objects.get_active(
            network_id=user.network_id,
            employee__user=user,
        ).annotate(
            group_id=Coalesce(F('function_group_id'),F('position__group_id'))
        ).values_list("group_id", flat=True)
        return FunctionGroup.objects.filter(group__in=groups).distinct('func')

    @action(detail=False, methods=['get'])
    def functions(self, request):
        return Response(FunctionGroup.FUNCS_TUPLE)


class WorkerPositionViewSet(UpdateorCreateViewSet):
    permission_classes = [Permission]
    serializer_class = WorkerPositionSerializer
    pagination_class = LimitOffsetPagination
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['WorkerPosition', 'Integration',]

    def get_queryset(self):
        include_clients = self.request.query_params.get('include_clients')
        include_outsources = self.request.query_params.get('include_outsources')
        network_filter = Q(network_id=self.request.user.network_id)
        if include_clients:
            network_filter |= Q(
                network_id__in=NetworkConnect.objects.filter(
                    outsourcing_id=self.request.user.network_id, 
                    allow_choose_shop_from_client_for_employement=True,
                ).values_list('client_id', flat=True)
            )
        if include_outsources:
            network_filter |= Q(
                network_id__in=NetworkConnect.objects.filter(
                    client_id=self.request.user.network_id, 
                ).values_list('outsourcing_id', flat=True)
            )
        return WorkerPosition.objects.filter(
            network_filter,
            dttm_deleted__isnull=True,
        )


class SubscribeViewSet(BaseModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscribeSerializer
    filterset_class = SubscribeFilter
    openapi_tags = ['Subscribe',]

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
    http_method_names = ['get', 'put']
    openapi_tags = ['Notification',]

    def get_queryset(self):
        user = self.request.user
        return Notification.objects.filter(worker=user).select_related('event', 'event__worker_day_details', 'event__shop')


class ShopSettingsViewSet(BaseActiveNamedModelViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = ShopSettingsSerializer
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['ShopSettings',]

    def get_queryset(self):
        user = self.request.user
        return ShopSettings.objects.filter(
            network_id=user.network_id
        )


class NetworkViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = NetworkSerializer
    queryset = Network.objects.all()
    openapi_tags = ['Network',]


class GroupViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = GroupSerializer
    pagination_class = LimitOffsetPagination
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['Group',]
    
    def get_queryset(self):
        return Group.objects.filter(
            network_id=self.request.user.network_id,
        )


class BreakViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = BreakSerializer
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['Break',]

    def get_queryset(self):
        return Break.objects.filter(
            network_id=self.request.user.network_id,
        )


class ShopScheduleViewSet(UpdateorCreateViewSet):
    permission_classes = [Permission]
    serializer_class = ShopScheduleSerializer
    filterset_class = ShopScheduleFilter
    openapi_tags = ['ShopSchedule',]

    lookup_field = 'dt'
    lookup_url_kwarg = 'dt'

    def get_queryset(self):
        return ShopSchedule.objects.filter(
            shop_id=self.kwargs.get('department_pk'), shop__network_id=self.request.user.network_id)

    def _perform_create_or_update(self, serializer):
        serializer.save(
            modified_by=self.request.user,
            shop_id=self.kwargs.get('department_pk'),
            dt=self.kwargs.get('dt'),
        )
        recalc_wdays.delay(
            shop_id=self.kwargs.get('department_pk'),
            dt__gte=self.kwargs.get('dt'),
            dt__lte=self.kwargs.get('dt'),
        )

    def perform_create(self, serializer):
        self._perform_create_or_update(serializer)

    def perform_update(self, serializer):
        self._perform_create_or_update(serializer)
