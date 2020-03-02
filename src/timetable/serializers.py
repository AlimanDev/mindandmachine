from rest_framework import serializers

from src.timetable.models import WorkerDay, WorkerDayCashboxDetails


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerDayCashboxDetails
        fields = ['id', 'work_type_id', 'dttm_from', 'dttm_to', 'status']

class WorkerDaySerializer(serializers.ModelSerializer):
    worker_day_details = WorkerDayCashboxDetailsSerializer(many=True)
    class Meta:
        model = WorkerDay
        fields = ['id', 'worker', 'shop', 'employment', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'worker_day_approve_id', 'worker_day_details']
