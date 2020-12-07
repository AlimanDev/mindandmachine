from django.db import models

from src.base.models_abstract import AbstractActiveNamedModel


class SmtpServerSettings(AbstractActiveNamedModel):
    email_default_from = models.CharField(verbose_name='from:', max_length=100, null=True, blank=True)
    email_host = models.CharField(verbose_name='Хост', max_length=100, null=True, blank=True)
    email_port = models.IntegerField(verbose_name='Порт', null=True, blank=True)
    email_username = models.CharField(verbose_name='Имя пользователя', max_length=100, null=True, blank=True)
    email_password = models.CharField(verbose_name='Пароль', max_length=100, null=True, blank=True)
    email_use_ssl = models.BooleanField(verbose_name='Использовать SSL', default=False)
    email_use_tls = models.BooleanField(verbose_name='Использовать TLS', default=False)
    email_fail_silently = models.BooleanField(default=False, verbose_name='Тихое подавление ошибок')
    email_timeout = models.IntegerField(verbose_name='Тайм-аут', null=True, blank=True)
    email_ssl_certfile = models.FileField(max_length=500, upload_to='SmtpEmailBackend/certfile/%Y/%m/%d',
                                          verbose_name='Сертификат', null=True, blank=True)
    email_ssl_keyfile = models.FileField(max_length=500, upload_to='SmtpEmailBackend/keyfile/%Y/%m/%d',
                                         verbose_name='Файл ключа', null=True, blank=True)

    class Meta:
        verbose_name = 'Настройки SMTP-сервера'
        verbose_name_plural = 'Настройки SMTP-сервера'

    def get_smtp_server_settings(self):
        server_settings = {
            'host': self.email_host,
            'port': self.email_port,
            'username': self.email_username,
            'password': self.email_password,
            'use_ssl': self.email_use_ssl,
            'use_tls': self.email_use_tls,
            'fail_silently': self.email_fail_silently,
            'timeout': self.email_timeout,
        }

        if self.email_ssl_certfile:
            server_settings['ssl_certfile'] = self.email_ssl_certfile.path

        if self.email_ssl_keyfile:
            server_settings['ssl_keyfile'] = self.email_ssl_keyfile.path

        for key, value in list(server_settings.items()):
            if value == '':
                server_settings[key] = None

        return server_settings
