import json
from io import BytesIO

import pandas as pd
from django.contrib.contenttypes.models import ContentType

from src.base.models import Shop
from src.integration.models import ExternalSystem, GenericExternalCode
from .base import BaseImportStrategy


class BaseSystemImportStrategy(BaseImportStrategy):
    def __init__(self, settings_json, **kwargs):
        self.settings_dict = json.loads(settings_json)
        super(BaseSystemImportStrategy, self).__init__(**kwargs)


class PobedaImportShopMapping(BaseSystemImportStrategy):
    def execute(self):
        filename = self.settings_dict.get('filename')
        file_content = self.fs_engine.read_file(filename)

        results = {}

        df = pd.read_excel(BytesIO(file_content), engine='xlrd')
        shop_code_1s_field_name = self.settings_dict.get('shop_code_1s_field_name')
        shop_number_run_field_name = self.settings_dict.get('shop_number_run_field_name')
        shops_dict = {s.code: s for s in Shop.objects.filter(code__in=list(df[shop_code_1s_field_name].values))}

        pobeda_external_system, _created = ExternalSystem.objects.get_or_create(
            code='pobeda', defaults={'name': 'Победа'})

        for index, row in df.iterrows():
            shop_code = row[shop_code_1s_field_name]
            shop = shops_dict.get(shop_code)
            if not shop:
                results.setdefault('errors', []).append(f'no shop with code="{shop_code}"')
                continue

            GenericExternalCode.objects.update_or_create(
                external_system=pobeda_external_system,
                object_id=shop.id,
                object_type=ContentType.objects.get_for_model(shop),
                defaults=dict(
                    code=row[shop_number_run_field_name]
                )
            )
        return results


SYSTEM_IMPORT_STRATEGIES_DICT = {
    'pobeda_import_shop_mapping': PobedaImportShopMapping,
}
