from django.core.management.base import BaseCommand
from src.db.works.parser.one import shop_01_users
from src.db.works.parser.one import shop_01_speed
from src.db.works.parser.one import shop_01_demand


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        shop_01_users.run()
        shop_01_speed.run()
        shop_01_demand.run()
