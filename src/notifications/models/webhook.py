from src.base.models_abstract import AbstractActiveNetworkSpecificCodeNamedModel


class WebhookSettings(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta:
        verbose_name = 'Настройки WebHook'
        verbose_name_plural = 'Настройки WebHook'
