from rest_framework.exceptions import APIException

class RecognitionError(APIException):
    status_code = 400
