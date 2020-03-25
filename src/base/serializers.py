from rest_framework import serializers
from src.base.models import  Employment, User, FunctionGroup, WorkerPosition
from src.timetable.serializers import WorkerWorkTypeSerializer, WorkerConstraintSerializer

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'middle_name',
                  'birthday', 'sex', 'avatar', 'email', 'phone_number','tabel_code']


class FunctionGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunctionGroup
        fields = [ 'id', 'group_id', 'func', 'method']


class EmploymentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    position_id = serializers.IntegerField(required=False)
    shop_id = serializers.IntegerField(required=False)
    user_id = serializers.IntegerField(required=False)
    work_types = WorkerWorkTypeSerializer(many=True)
    worker_constraints = WorkerConstraintSerializer(many=True)

    class Meta:
        model = Employment
        fields = ['id', 'user_id', 'shop_id', 'position_id', 'is_fixed_hours', 'dt_hired', 'dt_fired',
                  'salary', 'week_availability', 'norm_work_hours', 'min_time_btw_shifts',
                  'shift_hours_length_min', 'shift_hours_length_max', 'auto_timetable', 'tabel_code', 'is_ready_for_overworkings',
                  'dt_new_week_availability_from', 'user', 'is_visible',  'worker_constraints', 'work_types'
        ]
        create_only_fields = ['user_id', 'shop_id']
        read_only_fields=['user']

    def __init__(self, *args, **kwargs):
        super(EmploymentSerializer, self).__init__(*args, **kwargs)

        show_constraints = self.context['request'].query_params.get('show_constraints')
        if not show_constraints:
            self.fields.pop('worker_constraints')

    def to_internal_value(self, data):
        data = super(EmploymentSerializer, self).to_internal_value(data)
        if self.instance:
            # update
            for field in self.Meta.create_only_fields:
                if field in data:
                    data.pop(field)
        else:
            # shop_id is required for create
            for field in self.Meta.create_only_fields:
                if field not in data:
                    raise serializers.ValidationError({field:"This field is required"})
        return data


class WorkerPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerPosition
        fields = ['id', 'name',]
