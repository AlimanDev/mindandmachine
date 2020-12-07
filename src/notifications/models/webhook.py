from src.base.models_abstract import AbstractNamedModel


class WebhookSettings(AbstractNamedModel):
    class Meta:
        verbose_name = 'Настройки WebHook'
        verbose_name_plural = 'Настройки WebHook'
