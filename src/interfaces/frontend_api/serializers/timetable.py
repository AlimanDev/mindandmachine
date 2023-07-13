from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class TimetableHeaderFilterSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    start_date = serializers.DateField(format=settings.QOS_DATE_FORMAT)
    end_date = serializers.DateField(format=settings.QOS_DATE_FORMAT)

    def is_valid(self, *args, **kwargs):
        super(TimetableHeaderFilterSerializer, self).is_valid(*args, **kwargs)

        if self.validated_data['start_date'] > self.validated_data['end_date']:
            raise serializers.ValidationError(_('Date start should be less then date end'))


class DaySerializer(serializers.Serializer):
    date = serializers.DateField(format=settings.QOS_DATE_FORMAT)
    day_name = serializers.CharField()


class EfficiencyMetricsSerializer(serializers.Serializer):
    date = serializers.CharField()
    coverage = serializers.CharField(source='covering')
    downtime = serializers.CharField(source='deadtime')
    work_hours_by_load = serializers.CharField(source='predict_hours')
    hours_without_opened_vacancies = serializers.CharField(source='graph_hours')
    hours_with_opened_vacancies = serializers.CharField(source='graph_hours')
    hours_with_breaks = serializers.CharField(source='work_hours')
    employees_count_without_opened_vacancies = serializers.CharField(source='work_days')
    turnover = serializers.CharField(source='income')
    productivity = serializers.CharField(source='perfomance')


class TimetableHeaderDataSerializer(serializers.Serializer):
    days = DaySerializer(many=True)
    efficiency_metrics = EfficiencyMetricsSerializer(many=True)

    def to_representation(self, instance):
        data = super(TimetableHeaderDataSerializer, self).to_representation(instance)
        result = []
        for metrics_tuple in data['efficiency_metrics']:
            metrics_dict = {}
            print(metrics_tuple)
            for key, value in metrics_tuple.items():
                metrics_dict[key] = value
            result.append(metrics_dict)

        data['efficiency_metrics'] = result
        return data
