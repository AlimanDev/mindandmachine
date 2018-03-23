import json
import datetime

from django.http import HttpResponse


class JsonResponse(object):
    @classmethod
    def success(cls, data):
        return cls.base_response(200, data)

    @classmethod
    def value_error(cls, msg):
        return JsonResponse.base_error_response(400, 'ValueException', msg)

    @classmethod
    def base_error_response(cls, code, error_type, error_message):
        response_data = {
            'error_type': error_type,
            'error_message': error_message
        }
        return cls.base_response(code, response_data)

    @classmethod
    def base_response(cls, code, data):
        response_data = {
            'code': code,
            'data': data
        }
        return HttpResponse(json.dumps(response_data, separators=(',', ':')), content_type="application/json")


class ParseRequest(object):
    @classmethod
    def get_simple_param(cls, dictionary, key, constructor, prev_error=None):
        if prev_error is not None:
            return None, prev_error

        param = dictionary.get(key)
        if param is None:
            return None, JsonResponse.value_error('Key <{}> is missed'.format(key))

        if constructor is not None:
            try:
                param = constructor(param)
            except:
                return None, JsonResponse.value_error('Key <{}> value <{}> is invalid'.format(key, param))

        return param, None

    @classmethod
    def get_match_param(cls, dictionary, key, constructor, collection, prev_error=None):
        param, e = cls.get_simple_param(dictionary, key, constructor, prev_error)
        if e is not None:
            return None, e

        if param not in collection:
            return None, JsonResponse.value_error('Key <{}> with value <{}> does not match <{}>'.format(key, param, collection))

        return param, None


def parse_date(s):
    return datetime.datetime.strptime(s, "%d.%m.%Y")


def count(collection, comparer):
    c = 0
    for x in collection:
        if comparer(x):
            c += 1
    return c
