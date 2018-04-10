import os

from django.core.management.base import BaseCommand

from src.db.works.parser.one import shop_01_users
from src.db.works.parser.one import shop_01_speed
from src.db.works.parser.one import shop_01_demand

from src.db.works.parser.two import shop_003
from src.db.works.parser.three import shop_004


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
        # shop_003.run()
        shop_004.run()
