import os

from django.core.management.base import BaseCommand

from src.db.works.parser.shop_003 import shop_003
from src.db.works.parser.shop_004 import run as run_shop_004


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        os.system('./manage.py flush --noinput')
        print('Old database flushed')
        # shop_01_users.run()
        # shop_01_speed.run()
        # shop_01_demand.run()
        shop_003.run()
        run_shop_004.run()
