import json
import datetime

from django.http import HttpResponse


class JsonResponse(object):
    @classmethod
    def success(cls, data):
        return cls.__base_response(200, data)

    @classmethod
    def value_error(cls, key, value):
        if value is None:
            msg = 'Key <{}> is missing'.format(key)
        else:
            msg = 'Key <{}>, value <{}>'.format(key, value)

        return cls.__base_error_response(400, 'ValueException', msg)

    @classmethod
    def __base_error_response(cls, code, error_type, error_message):
        response_data = {
            'error_type': error_type,
            'error_message': error_message
        }
        return cls.__base_response(code, response_data)

    @classmethod
    def __base_response(cls, code, data):
        response_data = {
            'code': code,
            'data': data
        }
        return HttpResponse(json.dumps(response_data, separators=(',', ':')), content_type="application/json")


def get_param_or_error_response(dictionary, key, constructor, prev_error_response=None):
    if prev_error_response is not None:
        return None, prev_error_response

    try:
        return constructor(dictionary[key]), None
    except:
        return None, JsonResponse.value_error(key, dictionary.get(key, None))


def parse_date(s):
    return datetime.datetime.strptime(s, "%d.%m.%Y")
