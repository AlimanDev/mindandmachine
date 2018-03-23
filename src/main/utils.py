import json
import datetime

from django.http import HttpResponse


def json_response(code, data):
    json_data = {
        'meta': {
            'code': code
        },
        'data': data
    }
    return HttpResponse(json.dumps(json_data, separators=(',', ':')), content_type="application/json")


def parse_date(s):
    return datetime.datetime.strptime(s, "%d.%m.%Y")
