from rest_framework import serializers

from src.base.models import (
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleDayItem,
)


class ShiftScheduleDayItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftScheduleDayItem
        fields = (
            'id',
            'code',
            'hours_type',
            'hours_amount',
        )


class ShiftScheduleDaySerializer(serializers.ModelSerializer):
    items = ShiftScheduleDayItemSerializer(many=True)

    class Meta:
        model = ShiftScheduleDay
        fields = (
            'id',
            'code',
            'dt',
            'items',
        )


class ShiftScheduleSerializer(serializers.ModelSerializer):
    days = ShiftScheduleDaySerializer(many=True)

    class Meta:
        model = ShiftSchedule
        fields = (
            'id',
            'code',
            'name',
            'year',
            'days',
        )
