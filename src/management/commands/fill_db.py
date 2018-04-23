import os

from django.core.management.base import BaseCommand

from src.db.works.parser.shop_003.run import run as run_shop_003
from src.db.works.parser.shop_004.run import run as run_shop_004
from src.db.works.parser.shop_magnit.run import run as run_magnit


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        os.system('./manage.py flush --noinput')
        print('Old database flushed')

        run_shop_003()
        run_shop_004()
        run_magnit()
