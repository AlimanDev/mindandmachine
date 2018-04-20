import os

from django.core.management.base import BaseCommand

from src.db.works.parser.shop_003.run_2 import run as run_shop_003


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        run_shop_003()
