from src.util.test import LocalTestCase
import io
import pandas
from django.utils import timezone
import datetime
from src.conf.djconfig import QOS_DATE_FORMAT

class TestDownload(LocalTestCase):

    def setUp(self):
        super().setUp()

    def api_get(self, *args, **kwargs):
        response = self.client.get(*args, **kwargs)
        return response

    def test_get_tabel(self):
        self.auth()

        response = self.api_get('/api/download/get_tabel?weekday={}&shop_id=1'.format(
            datetime.date.strftime(timezone.now(), QOS_DATE_FORMAT)))
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[1]][14], 'Дурак Иван None')


    def test_get_demand_xlsx(self):
        self.auth()

        response = self.api_get('/api/download/get_demand_xlsx?from_dt=30.05.2019&to_dt=02.06.2019&shop_id=1&demand_model=C')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[0]][0], 'Кассы')
        self.assertEqual(tabel[tabel.columns[1]][0], '30.05.2019 00:00:00')

    def test_get_urv_xlsx(self):
        self.auth()

        response = self.api_get('/api/download/get_urv_xlsx?from_dt=30.05.2019&to_dt=02.06.2019&shop_id=1')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[0]][0], '01.06.2019')
        self.assertEqual(tabel[tabel.columns[1]][0], 'Дурак Иван')
        self.assertEqual(tabel[tabel.columns[2]][0], '09:00')
        self.assertEqual(tabel[tabel.columns[3]][0], 'пришел')

    def test_get_supershops_stats(self):
        self.auth()

        response = self.api_get('/api/download/get_supershops_stats?format=excel&pointer=1&items_per_page=1&revenue=-&lack=-&fot=-&idle=-&workers_amount=-&fot_revenue=-')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[0]][0], 'SuperShop1, ')