import os

from django.test import TestCase

from src.base.tests.factories import (
    ShopFactory,
)
from src.exchange.models import SystemImportStrategy, ImportJob, LocalFilesystemConnector
from src.integration.models import GenericExternalCode
from src.util.mixins.tests import TestsHelperMixin


class TestImportShopMapping(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.shop1_code = '22e9b174-8188-11eb-80ba-0050568a6492'
        cls.shop1 = ShopFactory(code=cls.shop1_code)
        cls.shop2_code = '07e6d8fc-87d9-11eb-80bb-0050568a6492'
        cls.shop2 = ShopFactory(code=cls.shop2_code)

        cls.local_fs_connector = LocalFilesystemConnector.objects.create(
            name='local',
        )
        cls.import_strategy = SystemImportStrategy.objects.create(
            strategy_type='pobeda_import_shop_mapping',
            settings_json=cls.dump_data(dict(
                filename=os.path.join('src', 'exchange', 'tests', 'files', 'division.xlsx'),  # можно относительный путь
                shop_code_1s_field_name='GUID в 1С',
                shop_number_run_field_name='Код магазина',
            )),
        )
        cls.import_job = ImportJob.objects.create(
            fs_connector=cls.local_fs_connector,
            import_strategy=cls.import_strategy,
        )

    def test_import_shop_mapping(self):
        results = self.import_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='pobeda').count(), 2)
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop1.id,
            external_system__code='pobeda',
            code='498').exists())
        self.assertTrue(GenericExternalCode.objects.filter(
            object_id=self.shop2.id,
            external_system__code='pobeda',
            code='482').exists())

        self.assertEqual(len(results.get('errors')), 1)
        self.assertEqual(results['errors'][0], 'no shop with code="Код, которого нету"')

        self.import_job.run()
        self.assertEqual(GenericExternalCode.objects.filter(external_system__code='pobeda').count(), 2)
