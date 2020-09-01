from django.utils import timezone
from django.db.models import Q
from src.base.models import Employment


class CurrentUserNetwork:
    requires_context = True

    def __call__(self, serializer_field):
        return serializer_field.context['request'].user.network_id



class UserworkShop:
    requires_context = True

    def __call__(self, serializer_field):
        now_day = timezone.now().date()
        employment =  Employment.objects.filter(
            Q(dt_fired__gte=now_day) | Q(dt_fired__isnull=True),
            user_id=serializer_field.context['request'].user.id,
        ).first()
        return employment.shop_id if employment else None

