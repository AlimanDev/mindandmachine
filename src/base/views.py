from rest_framework import mixins
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet, GenericViewSet
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_auth.views import UserDetailsView

from src.base.permissions import Permission
from src.base.serializers import EmploymentSerializer, UserSerializer, FunctionGroupSerializer, WorkerPositionSerializer, NotificationSerializer, SubscribeSerializer
from src.base.filters import EmploymentFilter, UserFilter, NotificationFilter, SubscribeFilter

from src.base.models import  Employment, User, FunctionGroup, WorkerPosition, Subscribe, Notification

from django.utils.timezone import now


class EmploymentViewSet(ModelViewSet):
    permission_classes = [Permission]
    serializer_class = EmploymentSerializer
    filterset_class = EmploymentFilter

    queryset = Employment.objects.all()


class UserViewSet(ModelViewSet):
    page_size = 10
    pagination_class = LimitOffsetPagination
    permission_classes = [IsAuthenticated]
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


class WorkerPositionViewSet(ReadOnlyModelViewSet):
    """

    GET /rest_api/work_type/
    :params
        shop_id: int, required=False
    :return [
        {
            "id": 2,
            "priority": 23,
            "dttm_last_update_queue": None,
            "min_workers_amount": 2,
            "max_workers_amount": 10,
            "probability": 2.0,
            "prior_weigth": 1.0,
            "shop_id": 1,
            "work_type_name":{
                "id": 1,
                "name": "Work type",
                "code": "1",
            }
        },
        ...
    ]


    GET /rest_api/work_type/6/
    :return {
        "id": 6,
        "priority": 23,
        "dttm_last_update_queue": None,
        "min_workers_amount": 2,
        "max_workers_amount": 10,
        "probability": 2.0,
        "prior_weigth": 1.0,
        "shop_id": 1,
        "work_type_name":{
            "id": 1,
            "name": "Work type",
            "code": "1",
        }
    }


    POST /rest_api/work_type/
    :params
        priority: int, required=False
        min_workers_amount: int, required=False
        max_workers_amount: int, required=False
        probability: float, required=Fasle
        prior_weigth: float, required=False
        shop_id: int, required=True
        code: str, required=False
        work_type_name_id: int, required=False
    :return
        code 201
        {
            "id": 6,
            "priority": 23,
            "dttm_last_update_queue": None,
            "min_workers_amount": 2,
            "max_workers_amount": 10,
            "probability": 2.0,
            "prior_weigth": 1.0,
            "shop_id": 1,
            "work_type_name":{
                "id": 1,
                "name": "Work type",
                "code": "1",
            }
        }


    PUT /rest_api/work_type/6/
    :params
        priority: int, required=False
        min_workers_amount: int, required=False
        max_workers_amount: int, required=False
        probability: float, required=Fasle
        prior_weigth: float, required=False
        shop_id: int, required=True
        code: str, required=False
        work_type_name_id: int, required=False
    :return {
        "id": 6,
        "priority": 23,
        "dttm_last_update_queue": None,
        "min_workers_amount": 2,
        "max_workers_amount": 10,
        "probability": 2.0,
        "prior_weigth": 1.0,
        "shop_id": 1,
        "work_type_name":{
            "id": 1,
            "name": "Work type",
            "code": "1",
        }
    }


    DELETE /rest_api/work_type/6/
    :return
        code 204

    """
    permission_classes = [IsAuthenticated]
    serializer_class = WorkerPositionSerializer
    queryset = WorkerPosition.objects.filter(dttm_deleted__isnull=True)


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
        return Notification.objects.filter(worker=user)
