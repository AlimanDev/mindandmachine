import datetime
from django.core.management.base import BaseCommand, CommandError
from src.db.models import Shop, Slot

class Command(BaseCommand):
  help = 'Update cashier info'

  def handle(self, *args, **options):
    data = {
      '003': {
        'd003': [
          { 'name': '1-я смена', 'tm_start': datetime.time(hour=7), 'tm_end': datetime.time(hour=16) },
          { 'name': '2-я смена', 'tm_start': datetime.time(hour=8), 'tm_end': datetime.time(hour=17) },
          { 'name': '3-я смена', 'tm_start': datetime.time(hour=13), 'tm_end': datetime.time(hour=22) },
          { 'name': '4-я смена', 'tm_start': datetime.time(hour=15), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': '7-я смена', 'tm_start': datetime.time(hour=7), 'tm_end': datetime.time(hour=18) },
          { 'name': '9-я смена', 'tm_start': datetime.time(hour=13), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': '10-я смена', 'tm_start': datetime.time(hour=22), 'tm_end': datetime.time(hour=6) },
        ],
        'd007': [
          { 'name': '1-я смена', 'tm_start': datetime.time(hour=7), 'tm_end': datetime.time(hour=16) },
          { 'name': '2-я смена', 'tm_start': datetime.time(hour=11), 'tm_end': datetime.time(hour=20) },
          { 'name': '3-я смена', 'tm_start': datetime.time(hour=15), 'tm_end': datetime.time(hour=23, minute=59) },
        ],
        'd012': [
          { 'name': '1-я смена', 'tm_start': datetime.time(hour=7), 'tm_end': datetime.time(hour=16) },
          { 'name': '2-я смена', 'tm_start': datetime.time(hour=9), 'tm_end': datetime.time(hour=18) },
          { 'name': '3-я смена', 'tm_start': datetime.time(hour=13), 'tm_end': datetime.time(hour=22) },
          { 'name': '4-я смена', 'tm_start': datetime.time(hour=15), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': '5-я смена', 'tm_start': datetime.time(hour=10), 'tm_end': datetime.time(hour=19) },
          { 'name': 'У смена', 'tm_start': datetime.time(hour=7), 'tm_end': datetime.time(hour=19) },
          { 'name': 'ВЧ смена', 'tm_start': datetime.time(hour=12), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': 'Д смена', 'tm_start': datetime.time(hour=12), 'tm_end': datetime.time(hour=21) },
        ],
      },
      '004': {
        'd003': [
          { 'name': 'У', 'tm_start': datetime.time(hour=7, minute=30), 'tm_end': datetime.time(hour=16, minute=30) },
          { 'name': 'У3', 'tm_start': datetime.time(hour=7, minute=30), 'tm_end': datetime.time(hour=19, minute=30) },
          { 'name': 'д', 'tm_start': datetime.time(hour=10), 'tm_end': datetime.time(hour=19) },
          { 'name': 'в1', 'tm_start': datetime.time(hour=13), 'tm_end': datetime.time(hour=22) },
          { 'name': 'в2', 'tm_start': datetime.time(hour=15), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': 'в3', 'tm_start': datetime.time(hour=12, minute=30), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': 'н', 'tm_start': datetime.time(hour=21), 'tm_end': datetime.time(hour=9) },
        ],
        'd007': [
          { 'name': 'У', 'tm_start': datetime.time(hour=7, minute=30), 'tm_end': datetime.time(hour=16, minute=30) },
          { 'name': 'У3', 'tm_start': datetime.time(hour=7, minute=30), 'tm_end': datetime.time(hour=19, minute=30) },
          { 'name': 'д', 'tm_start': datetime.time(hour=10), 'tm_end': datetime.time(hour=19) },
          { 'name': 'в1', 'tm_start': datetime.time(hour=13), 'tm_end': datetime.time(hour=22) },
          { 'name': 'в2', 'tm_start': datetime.time(hour=15), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': 'в3', 'tm_start': datetime.time(hour=12, minute=30), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': 'н', 'tm_start': datetime.time(hour=21), 'tm_end': datetime.time(hour=9) },
        ],
        'd012': [
          { 'name': 'У', 'tm_start': datetime.time(hour=7), 'tm_end': datetime.time(hour=16) },
          { 'name': 'у1', 'tm_start': datetime.time(hour=8), 'tm_end': datetime.time(hour=17) },
          { 'name': 'д', 'tm_start': datetime.time(hour=10), 'tm_end': datetime.time(hour=19) },
          { 'name': 'в2', 'tm_start': datetime.time(hour=15), 'tm_end': datetime.time(hour=23, minute=59) },
          { 'name': 'н', 'tm_start': datetime.time(hour=21), 'tm_end': datetime.time(hour=9) },
        ],
      },
    }
    slots = []
    for super_shop_code, super_shop_slots in data.items():
      for hidden_title, shop_slots in super_shop_slots.items():
        shop = Shop.objects.get(super_shop__code=super_shop_code, hidden_title=hidden_title)
        for slot_data in shop_slots:
          slots.append(Slot(
            tm_start=slot_data['tm_start'],
            tm_end=slot_data['tm_end'],
            name=slot_data['name'],
            shop=shop,
          ))
    Slot.objects.bulk_create(slots)