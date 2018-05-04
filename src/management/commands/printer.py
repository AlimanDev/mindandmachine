from django.core.management.base import BaseCommand

from src.db.models import SuperShop, Shop
from src.db.works.printer.run import run


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        super_shop = SuperShop.objects.get(hidden_title='shop004')
        shop = Shop.objects.get(super_shop=super_shop, hidden_title='d003')

        run(
            shop_id=shop.id,
            debug=True
        )
