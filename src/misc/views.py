from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
import jwt
import time

METABASE_SITE_URL = settings.METABASE_SITE_URL
METABASE_SECRET_KEY = settings.METABASE_SECRET_KEY


@api_view()
def metabase_url(request):
    # You'll need to install PyJWT via pip 'pip install PyJWT' or your project packages file


    payload = {
        "resource": {"dashboard": 3},
        "params": {

        },
        "exp": round(time.time()) + (60 * 60)  # 1 hour expiration
    }
    token = jwt.encode(payload, METABASE_SECRET_KEY, algorithm="HS256")

    iframeUrl = METABASE_SITE_URL + "/embed/dashboard/" + token.decode("utf8") + "#bordered=false&titled=false&hide_parameters=shop_id"
    return Response({"url": iframeUrl})
