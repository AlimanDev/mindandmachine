from rest_framework.exceptions import ValidationError
from src.base.message import Message


class MessageError(ValidationError):
    def __init__(self, code=None, params={}, lang='ru', detail=None ):
        super().__init__(detail, code)
        m = Message(lang=lang)
        message = m.get_message(code, params)
        self.detail = {"message": message}
