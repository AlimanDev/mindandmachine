import datetime
from .models import (
    CameraCashboxStat,
    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
)
from .tasks import (
    update_queue,
    update_visitors_info,
    clean_camera_stats,
)
import datetime
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()

        months_ago = now() - relativedelta(months=3)
        for i in range(100):
            CameraCashboxStat.objects.create(
                camera_cashbox=self.camera_cashbox,
                dttm=months_ago - datetime.timedelta(hours=i),
                queue=i
            )


    def test_update_queue(self):
        dttm_now = now() + datetime.timedelta(hours=3)

        if not len(WorkType.objects.filter(dttm_last_update_queue__isnull=False)):
            with self.assertRaises(ValueError) as cm:
                update_queue()
            raise Exception(cm.exception)

        update_queue()

        updated_cashbox_types = WorkType.objects.qos_filter_active(
            dttm_now + datetime.timedelta(minutes=30),
            dttm_now,
            dttm_last_update_queue__isnull=False,
        )
        for update_time in updated_cashbox_types.values_list('dttm_last_update_queue', flat=True):
            self.assertEqual(
                update_time,
                dttm_now.replace(minute=0 if dttm_now.minute < 30 else 30, second=0, microsecond=0)
            )
        for cashbox_type in WorkType.objects.filter(dttm_deleted__isnull=False):
            self.assertEqual(cashbox_type.dttm_last_update_queue, None)
        self.assertGreater(PeriodQueues.objects.count(), 0)

    # @skip("visitor info")
    def test_update_visitors_info(self):
        def check_amount(model, dttm):
            return model.objects.filter(dttm_forecast=dttm, type=PeriodQueues.FACT_TYPE).count()

        dttm_now = now()
        dttm = now().replace(minute=0 if dttm_now.minute < 30 else 30, second=0, microsecond=0)
        update_visitors_info()

        self.assertEqual(check_amount(IncomeVisitors, dttm), 1)
        self.assertEqual(check_amount(EmptyOutcomeVisitors, dttm), 1)
        self.assertEqual(check_amount(PurchasesOutcomeVisitors, dttm), 1)

    def test_clean_camera_stats(self):
        stats = CameraCashboxStat.objects.filter(dttm__lt=now() - relativedelta(months=3))
        self.assertEqual(stats.count(), 100)
        clean_camera_stats()
        stats = CameraCashboxStat.objects.filter(dttm__lt=now() - relativedelta(months=3))
