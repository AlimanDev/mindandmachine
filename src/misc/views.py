from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import Serializer, CharField, URLField
from django.conf import settings
import jwt
import time
from drf_yasg.utils import swagger_auto_schema

class MetabaseURLSerialzier(Serializer):
    dashboard = CharField(default='worker_day', help_text='На данный момент доступно 2 дашборда: worker_day и indicator')
# METABASE_SITE_URL = settings.METABASE_SITE_URL
# METABASE_SECRET_KEY = settings.METABASE_SECRET_KEY

class MetabaseResponseSerializer(Serializer):
    url = URLField(
        default='https://metabase.example.com/embed/dashboard/{token}#bordered=false&titled=false&hide_parameters=shop_id,vacancy,dt,worker_id,employee_id',
        help_text='Ссылка с токеном для доступа к metabase',
    )

@swagger_auto_schema(methods=['get'], query_serializer=MetabaseURLSerialzier, responses={200: MetabaseResponseSerializer})
@api_view()
def metabase_url(request):
    '''
    Возвращает ссылку с токеном для доступа к metabase
    '''
    # You'll need to install PyJWT via pip 'pip install PyJWT' or your project packages file

    dashboard = request.query_params.get('dashboard','worker_day')
    dashboard_dict = {
        'worker_day': 3,
        'indicator': 4
    }
    id = dashboard_dict.get(dashboard,None)
    if not id:
        raise ValidationError(f"dashboard {dashboard} does not exist")

    payload = {
        "resource": {"dashboard": id},
        "params": {

        },
        "exp": round(time.time()) + (60 * 60)  # 1 hour expiration
    }
    token = jwt.encode(payload, settings.METABASE_SECRET_KEY, algorithm="HS256")

    iframeUrl = settings.METABASE_SITE_URL + "/embed/dashboard/" + token.decode("utf8") + "#bordered=false&titled=false&hide_parameters=shop_id,vacancy,dt,worker_id,employee_id"
    return Response({"url": iframeUrl})
