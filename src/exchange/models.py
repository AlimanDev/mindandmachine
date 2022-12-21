import datetime as dt
import json
import typing as tp

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from polymorphic.models import PolymorphicModel
from src.base.models_abstract import AbstractModel
from src.exchange.fs_engines.ftp import FtpEngine
from src.exchange.fs_engines.local import LocalEngine


class BaseFilesystemConnector(PolymorphicModel):
    name = models.CharField(max_length=256, null=True, blank=True)

    def get_fs_engine(self, base_path=None):
        raise NotImplementedError

    def __str__(self):
        return self.name or str(self.id)

    class Meta:
        verbose_name = 'Коннектор к файловой системы'
        verbose_name_plural = 'Коннекторы к файловой системе'


class BaseJob(AbstractModel):
    base_path = models.CharField(blank=True, max_length=512)
    fs_connector = models.ForeignKey(BaseFilesystemConnector, on_delete=models.CASCADE)
    retry_attempts = models.TextField(default='{}')

    @property
    def retries(self):
        try:
            return json.loads(self.retry_attempts)
        except:
            return {}

    class Meta:
        abstract = True


class LocalFilesystemConnector(BaseFilesystemConnector):
    default_base_path = models.CharField(max_length=512, null=True, default=None)

    class Meta:
        verbose_name = 'Коннектор к локальной файловой системе'
        verbose_name_plural = 'Коннекторы к локальной файловой системе'

    def __str__(self):
        return self.name or f'local fs connector ({self.default_base_path})'

    def get_fs_engine(self, base_path=None):
        return LocalEngine(base_path=base_path or self.default_base_path or settings.BASE_DIR)


class FtpFilesystemConnector(BaseFilesystemConnector):
    default_base_path = models.CharField(max_length=512)
    host = models.CharField(max_length=128)
    port = models.PositiveSmallIntegerField(default=21)
    username = models.CharField(max_length=128)
    password = models.CharField(max_length=50)  # TODO: виджет пароля из from django import forms в админке

    class Meta:
        verbose_name = 'Коннектор к FTP'
        verbose_name_plural = 'Коннекторы к FTP'

    def __str__(self):
        return self.name or f'ftp fs connector {self.host}:{self.port} ({self.default_base_path})'

    def get_fs_engine(self, base_path=None):
        return FtpEngine(
            base_path=base_path or self.default_base_path,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
        )


class ImportStrategy(PolymorphicModel):
    name = models.CharField(max_length=256, null=True, blank=True)

    class Meta:
        verbose_name = 'Стратегия импорта'
        verbose_name_plural = 'Стратегии импорта'

    def __str__(self):
        return self.name or str(self.id)

    def get_strategy_cls_kwargs(self):
        return {}

    def get_strategy_cls(self):
        raise NotImplementedError


class ImportShopMappingStrategy(ImportStrategy):
    FILE_FORMAT_CHOICES = (
        ('xlsx', 'Excel (xlsx)'),
        ('csv', 'Comma-separated values (csv)'),
    )

    system_code = models.CharField(max_length=64, verbose_name='Код системы')
    system_name = models.CharField(max_length=128, verbose_name='Имя системы', null=True, blank=True)
    filename = models.CharField(max_length=256, verbose_name='Имя файла')
    file_format = models.CharField(
        max_length=8, verbose_name='Формат файла', choices=FILE_FORMAT_CHOICES, default='xlsx')
    csv_delimiter = models.CharField(max_length=1, verbose_name=_('csv delimiter'), null=True, blank=True)
    wfm_shop_code_field_name = models.CharField(
        max_length=256, verbose_name='Название поля кода магазина в WFM-системе', null=True, blank=True)
    wfm_shop_name_field_name = models.CharField(
        max_length=256, verbose_name='Название поля наименования магазина в WFM-системе', null=True, blank=True)
    external_shop_code_field_name = models.CharField(
        max_length=256, verbose_name='Название поля кода магазина в внешней системе')

    class Meta:
        verbose_name = 'Стратегия импорт сопоставления кодов магазинов'
        verbose_name_plural = 'Стратегии импорта сопоставления кодов магазинов'

    def clean(self):
        if not (self.wfm_shop_code_field_name or self.wfm_shop_name_field_name):
            raise ValidationError(_(
                'Одно из полей "Название поля кода магазина в WFM-системе" или '
                '"Название поля наименования магазина в WFM-системе" должно быть заполнено.'))

    def get_strategy_cls_kwargs(self):
        return {
            'system_code': self.system_code,
            'system_name': self.system_name or '',
            'filename': self.filename,
            'file_format': self.file_format,
            'csv_delimiter': self.csv_delimiter,
            'wfm_shop_code_field_name': self.wfm_shop_code_field_name,
            'wfm_shop_name_field_name': self.wfm_shop_name_field_name,
            'external_shop_code_field_name': self.external_shop_code_field_name,
        }

    def get_strategy_cls(self):
        from .import_strategies.system import ImportShopMappingStrategy
        return ImportShopMappingStrategy


class ImportHistDataStrategy(ImportStrategy):
    system_code = models.CharField(max_length=64, verbose_name='Код системы')
    data_type = models.CharField(max_length=64, verbose_name='Тип данных')
    separated_file_for_each_shop = models.BooleanField(verbose_name='Отдельный файл для каждого магазина', default=False)
    filename_fmt = models.CharField(
        max_length=256, verbose_name='Формат файла',
        help_text="Например: '{data_type}_{year:04d}{month:02d}{day:02d}.csv'",
    )
    dt_from = models.CharField(max_length=32, verbose_name='Дата от', default='today')
    dt_to = models.CharField(max_length=32, verbose_name='Дата до', default='today')
    csv_delimiter = models.CharField(max_length=1, verbose_name=_('csv delimiter'), default=';')
    columns = models.JSONField(
        null=True, blank=True,
        verbose_name='Наименование колонок в файле',
        help_text='Если не указано, то будет использоваться 1 строка как названия колонок',
    )
    shop_num_column_name = models.CharField(
        max_length=128, verbose_name='Наименование колонки с номером магазина')
    dt_or_dttm_column_name = models.CharField(
        max_length=128, verbose_name='Наименование колонки дата или дата+время')
    dt_or_dttm_format = models.CharField(
        max_length=128, verbose_name='Формат загрузки колонки дата или дата+время')
    receipt_code_columns = models.JSONField(
        null=True, blank=True,
        verbose_name='Колонки, используемые для ключа',
        help_text='Если не указано, то в качестве ключа будет использоваться хэш всех колонок',
    )
    fix_date = models.BooleanField(verbose_name='Нужно ли заменять дату внутри файла на ту, что в имени', default=False)
    use_total_discounted_price = models.BooleanField(verbose_name=_('Take into account the final discounted price in the object'), default=False)
    remove_duplicates_columns = models.JSONField(
        null=True, blank=True,
        verbose_name=_('Columns that act as a key when taking the final discounted price'))

    class Meta:
        verbose_name = 'Стратегия импорта исторических данных'
        verbose_name_plural = 'Стратегии импорта исторических данных'

    def get_strategy_cls_kwargs(self):
        return {
            'system_code': self.system_code,
            'data_type': self.data_type,
            'separated_file_for_each_shop': self.separated_file_for_each_shop,
            'filename_fmt': self.filename_fmt,
            'dt_from': self.dt_from,
            'dt_to': self.dt_to,
            'csv_delimiter': self.csv_delimiter,
            'shop_num_column_name': self.shop_num_column_name,
            'dt_or_dttm_column_name': self.dt_or_dttm_column_name,
            'dt_or_dttm_format': self.dt_or_dttm_format,
            'columns': self.columns,
            'receipt_code_columns': self.receipt_code_columns,
            'fix_date': self.fix_date,
            "use_total_discounted_price": self.use_total_discounted_price,
            "remove_duplicates_columns": self.remove_duplicates_columns
        }

    def get_strategy_cls(self):
        from .import_strategies.system import ImportHistDataStrategy
        return ImportHistDataStrategy


class ImportJob(BaseJob):
    import_strategy = models.ForeignKey(ImportStrategy, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Задача импорта данных'
        verbose_name_plural = 'Задачи импорта данных'

    def __str__(self):
        return f'{self.import_strategy}, {self.fs_connector}'

    def run(
        self,
        date_from: tp.Optional[dt.date] = None,
        date_to: tp.Optional[dt.date] = None,
    ):
        strategy_cls = self.import_strategy.get_strategy_cls()
        strategy_cls_kwargs = self.import_strategy.get_strategy_cls_kwargs()
        strategy_cls_kwargs['fs_engine'] = self.fs_connector.get_fs_engine(base_path=self.base_path)
        if (date_from is not None) and (date_to is not None):
            strategy_cls_kwargs.update({'dt_from': date_from, 'dt_to': date_to,})
        strategy = strategy_cls(**strategy_cls_kwargs)
        return strategy.execute()


class ExportStrategy(PolymorphicModel):
    name = models.CharField(max_length=256, null=True, blank=True)

    class Meta:
        verbose_name = 'Стратегия экспорта'
        verbose_name_plural = 'Стратегии экспорта'

    def __str__(self):
        return self.name or str(self.id)

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

    def __str__(self):
        return self.name or self.get_strategy_type_display() or str(self.id)

    def clean(self):
        period_needed_strategies = [SystemExportStrategy.WORK_HOURS_PIVOT_TABLE]
        if self.strategy_type in period_needed_strategies and self.period is None:
            raise ValidationError(_("For the '{}' strategy, you must select a period.").format(self.strategy_type)) # Для стратегии "{}" обязательно выбрать период.

    def get_strategy_cls_kwargs(self):
        kwargs = super(SystemExportStrategy, self).get_strategy_cls_kwargs()
        kwargs['settings_json'] = self.settings_json
        kwargs['period'] = self.period
        return kwargs

    def get_strategy_cls(self):
        from .export_strategies.system import SYSTEM_EXPORT_STRATEGIES_DICT
        return SYSTEM_EXPORT_STRATEGIES_DICT.get(self.strategy_type)


class ExportJob(BaseJob):
    export_strategy = models.ForeignKey(ExportStrategy, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Задача экспорта данных'
        verbose_name_plural = 'Задачи экспорта данных'

    def __str__(self):
        return f'{self.export_strategy}, {self.fs_connector}'

    def run(self):
        strategy_cls = self.export_strategy.get_strategy_cls()
        strategy_cls_kwargs = self.export_strategy.get_strategy_cls_kwargs()
        strategy_cls_kwargs['fs_engine'] = self.fs_connector.get_fs_engine(base_path=self.base_path)
        strategy = strategy_cls(**strategy_cls_kwargs)
        return strategy.execute()
