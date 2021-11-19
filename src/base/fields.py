import zlib
import base64

from django.utils import timezone
from django.db.models import Q, TextField


class CurrentUserNetwork:
    requires_context = True

    def __call__(self, serializer_field):
        return serializer_field.context['request'].user.network_id



class UserworkShop:
    requires_context = True

    def __call__(self, serializer_field):
        from src.base.models import Employment
        now_day = timezone.now().date()
        employment =  Employment.objects.filter(
            Q(dt_fired__gte=now_day) | Q(dt_fired__isnull=True),
            employee__user_id=serializer_field.context['request'].user.id,
        ).first()
        return employment.shop_id if employment else None


class CompressedTextField(TextField):
    def to_python(self, value):
        try:
            return zlib.decompress(base64.b64decode(bytes(value, 'utf-8'))).decode('utf-8')
        except:
            return value

    def value_from_object(self, obj):
        return self.to_python(getattr(obj, self.attname))

    def get_db_prep_save(self, value, connection):
        value = self.get_db_prep_value(value, connection=connection, prepared=False)
        return base64.b64encode(zlib.compress(bytes(value, 'utf-8'))).decode('utf-8')

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return self.to_python(value)

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)
