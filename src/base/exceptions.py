from rest_framework.exceptions import ValidationError
from src.base.message import Message


class MessageError(ValidationError):
    def __init__(self, detail=None, code=None, params={}, lang='ru'):
        super().__init__(detail, code)
        m = Message(lang=lang)
        message = m.get_message(code, params)
        self.detail = {"message": message}
