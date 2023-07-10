import json

class Message(object):
    LANGUAGES = ('ru')

    def __init__(self, lang='ru'):
        if lang not in self.LANGUAGES:
            raise Exception(f"Unknown language {lang}")
        file = open(f"data/lang/{lang}.json", encoding='utf-8')
        self.message_dict = json.load(file)

    def get_message(self, key, params={}):
        message = self.message_dict.get(key, None)
        if not message:
            return key
        message = message.format(**params)
        return message
