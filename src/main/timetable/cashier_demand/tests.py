import datetime
from src.util.test import LocalTestCase
from src.db.models import WorkerDayCashboxDetails, WorkerDay
from src.util.models_converter import BaseConverter


class TestCashierDemand(LocalTestCase):

    def setUp(self):
        super().setUp()

    def test_get_workers(self):
        def get_count(shop, time1, time2):
            count = len(WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
                worker_day__worker__shop_id=shop,
                worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
                dttm_from__lte=time1,
                dttm_to__gte=time2,
            ))
            return count
        self.auth()
        time1 = datetime.datetime(2018, 6, 15, 12, 30, 0)
        time2 = datetime.datetime(2018, 6, 15, 12, 55, 0)
        time3 = datetime.datetime(2018, 6, 15, 16, 30, 0)
        time4 = datetime.datetime(2018, 6, 15, 16, 55, 0)
        response = self.api_get('/api/timetable/needs/get_workers?shop_id=1&work_type_ids=[]&from_dttm={}&to_dttm={}'
                                .format(BaseConverter.convert_datetime(time1), BaseConverter.convert_datetime(time2)))
        len_wdcd = get_count(self.shop, time1, time2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        # Пустой response.json['data']
        # self.assertEqual(response.json['data']['users']['1']['u']['username'], 'user1')
        # self.assertEqual(len(response.json['data']['users']), len_wdcd)

        response = self.api_get('/api/timetable/needs/get_workers?shop_id=1&work_type_ids=[]&from_dttm={}&to_dttm={}'
                                .format(BaseConverter.convert_datetime(time3), BaseConverter.convert_datetime(time4)))
        len_wdcd = get_count(self.shop, time3, time4)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        # Пустой response.json['data']
        # self.assertEqual(response.json['data']['users']['1']['u']['username'], 'user1')
        # self.assertEqual(len(response.json['data']['users']), len_wdcd)

