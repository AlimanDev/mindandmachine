import datetime
import pandas
import numpy
from django.core.management.base import BaseCommand, CommandError
from src.db.models import Shop, Slot, User

class Command(BaseCommand):
  help = 'Update cashier info'

  def add_arguments(self, parser):
      parser.add_argument('shop_id', type=str)
      parser.add_argument('out_file', type=str)

  def handle(self, *args, **options):
      shop = Shop.objects.get(id=options['shop_id'])

      users = User.objects.filter(shop=shop)
