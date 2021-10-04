from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from polymorphic.models import PolymorphicModel

from src.base.models_abstract import AbstractModel
from src.exchange.fs_engines.ftp import FtpEngine
from src.exchange.fs_engines.local import LocalEngine


class BaseFilesystemConnector(PolymorphicModel):
    name = models.CharField(max_length=256)

    def get_fs_engine(self, base_path=None):
        raise NotImplementedError

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Коннектор к файловой системы'
        verbose_name_plural = 'Коннекторы к файловой системе'


class LocalFilesystemConnector(BaseFilesystemConnector):
    default_base_path = models.CharField(max_length=512, default=settings.BASE_DIR)

    def get_fs_engine(self, base_path=None):
        return LocalEngine(base_path=base_path or self.default_base_path)

    class Meta:
        verbose_name = 'Коннектор к локальной файловой системе'
        verbose_name_plural = 'Коннекторы к локальной файловой системе'


class FtpFilesystemConnector(BaseFilesystemConnector):
    default_base_path = models.CharField(max_length=512)
    host = models.CharField(max_length=128)
    port = models.PositiveSmallIntegerField(default=21)
    username = models.CharField(max_length=128)
    password = models.CharField(max_length=50)  # TODO: виджет пароля из from django import forms в админке

    def get_fs_engine(self, base_path=None):
        return FtpEngine(
            base_path=base_path or self.default_base_path,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
        )

    class Meta:
        verbose_name = 'Коннектор к FTP'
        verbose_name_plural = 'Коннекторы к FTP'


class ImportStrategy(PolymorphicModel):
    name = models.CharField(max_length=256)

    class Meta:
        verbose_name = 'Стратегия импорта'
        verbose_name_plural = 'Стратегии импорта'

    def __str__(self):
        return self.name

    def get_strategy_cls_kwargs(self):
        return {}

    def get_strategy_cls(self):
        raise NotImplementedError


class SystemImportStrategy(ImportStrategy):
    POBEDA_IMPORT_SHOP_MAPPING = 'pobeda_import_shop_mapping'
    POBEDA_IMPORT_PURCHASES = 'pobeda_import_purchases'
    POBEDA_IMPORT_BRAK = 'pobeda_import_brak'
    POBEDA_IMPORT_DELIVERY = 'pobeda_import_delivery'

    SYSTEM_IMPORT_STRATEGY_CHOICES = (
        (POBEDA_IMPORT_SHOP_MAPPING, 'Импорт сопоставления кодов магазинов (Победа)'),
        (POBEDA_IMPORT_PURCHASES, 'Импорт чеков (Победа)'),
        (POBEDA_IMPORT_BRAK, 'Импорт списаний (Победа)'),
        (POBEDA_IMPORT_DELIVERY, 'Импорт поставок (Победа)'),
    )

    settings_json = models.TextField(default='{}')
    strategy_type = models.CharField(max_length=128, choices=SYSTEM_IMPORT_STRATEGY_CHOICES)

    class Meta:
        verbose_name = 'Системная стратегия импорта'
        verbose_name_plural = 'Системные стратегии импорта'

    def get_strategy_cls_kwargs(self):
        kwargs = super(SystemImportStrategy, self).get_strategy_cls_kwargs()
        kwargs['settings_json'] = self.settings_json
        return kwargs

    def get_strategy_cls(self):
        from .import_strategies.system import SYSTEM_IMPORT_STRATEGIES_DICT
        return SYSTEM_IMPORT_STRATEGIES_DICT.get(self.strategy_type)


class ImportJob(AbstractModel):
    base_path = models.CharField(blank=True, max_length=512)
    import_strategy = models.ForeignKey(ImportStrategy, on_delete=models.CASCADE)
    fs_connector = models.ForeignKey(BaseFilesystemConnector, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Задача импорта данных'
        verbose_name_plural = 'Задачи импорта данных'

    def run(self):
        strategy_cls = self.import_strategy.get_strategy_cls()
        strategy_cls_kwargs = self.import_strategy.get_strategy_cls_kwargs()
        strategy_cls_kwargs['fs_engine'] = self.fs_connector.get_fs_engine(base_path=self.base_path)
        strategy = strategy_cls(**strategy_cls_kwargs)
        return strategy.execute()


class ExportStrategy(PolymorphicModel):
    name = models.CharField(max_length=256)

    class Meta:
        verbose_name = 'Стратегия экспорта'
        verbose_name_plural = 'Стратегии экспорта'

    def __str__(self):
        return self.name

    def get_strategy_cls_kwargs(self):
        return {}

    def get_strategy_cls(self):
        raise NotImplementedError


class SystemExportStrategy(ExportStrategy):
    WORK_HOURS_PIVOT_TABLE = 'work_hours_pivot_table'
    PLAN_AND_FACT_HOURS_TABLE = 'plan_and_fact_hours_table'

    SYSTEM_EXPORT_STRATEGY_CHOICES = (
        (WORK_HOURS_PIVOT_TABLE, 'Сводная таблица по отработанным часам по всем магазинам'),
        (PLAN_AND_FACT_HOURS_TABLE, 'Таблица по плановым и факт часам'),
    )

    period = models.ForeignKey('reports.Period', null=True, blank=True, on_delete=models.SET_NULL)
    settings_json = models.TextField(default='{}')
    strategy_type = models.CharField(max_length=128, choices=SYSTEM_EXPORT_STRATEGY_CHOICES)

    class Meta:
        verbose_name = 'Системная стратегия экспорта'
        verbose_name_plural = 'Системные стратегии экспорта'

    def clean(self):
        period_needed_strategies = [SystemExportStrategy.WORK_HOURS_PIVOT_TABLE]
        if self.strategy_type in period_needed_strategies and self.period is None:
            raise ValidationError(f'Для стратегии "{self.strategy_type}" обязательно выбрать период.')

    def get_strategy_cls_kwargs(self):
        kwargs = super(SystemExportStrategy, self).get_strategy_cls_kwargs()
        kwargs['settings_json'] = self.settings_json
        kwargs['period'] = self.period
        return kwargs

    def get_strategy_cls(self):
        from .export_strategies.system import SYSTEM_EXPORT_STRATEGIES_DICT
        return SYSTEM_EXPORT_STRATEGIES_DICT.get(self.strategy_type)


class ExportJob(AbstractModel):
    base_path = models.CharField(blank=True, max_length=512)
    export_strategy = models.ForeignKey(ExportStrategy, on_delete=models.CASCADE)
    fs_connector = models.ForeignKey(BaseFilesystemConnector, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Задача экспорта данных'
        verbose_name_plural = 'Задачи экспорта данных'

    def run(self):
        strategy_cls = self.export_strategy.get_strategy_cls()
        strategy_cls_kwargs = self.export_strategy.get_strategy_cls_kwargs()
        strategy_cls_kwargs['fs_engine'] = self.fs_connector.get_fs_engine(base_path=self.base_path)
        strategy = strategy_cls(**strategy_cls_kwargs)
        return strategy.execute()
