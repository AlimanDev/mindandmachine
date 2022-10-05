# Internalization

Django use out the box [internalization](https://docs.djangoproject.com/en/4.1/topics/i18n/).
Use internalization you should use [translation](https://docs.djangoproject.com/en/4.1/topics/i18n/translation/).

You must use `_` when using a string or other template using the frontend or django admin.

```python
from django.utils.translation import gettext_lazy as _
```

To make messages you should next command:
```shell
python manage.py makemessages --locale=ru -d django -i venv
```

This command change file `data/locale/ru/LC_MESSAGES/django.po`.
After this you should compile messages via command:
```shell
python manage.py compilemessages --locale=ru -i venv
```