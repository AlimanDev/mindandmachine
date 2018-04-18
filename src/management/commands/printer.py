from django.core.management.base import BaseCommand

from src.db.works.printer.run import run


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        run(
            shop_id=2
        )
