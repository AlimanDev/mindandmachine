from rest_framework import serializers

from src.base.models import Shop


class ShopDTOSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source='is_active')
    sap = serializers.CharField(source='code')
    locality = serializers.CharField(source='name')
    city = serializers.CharField()
    regionId = serializers.IntegerField(source='parent_id')
    allDay = serializers.BooleanField(source='is_all_day')
    directorLogin = serializers.SerializerMethodField()

    def get_directorLogin(self, shop):
        if shop.director_id:
            return shop.director.username

    class Meta:
        model = Shop
        fields = (
            'id',
            'active',
            'sap',
            'locality',
            'city',
            'regionId',
            'allDay',
            'directorLogin',
            'address',
            'latitude',
            'longitude',
            'email',  # TODO: нужно ли искать email директора салона, если нету в самом салоне?
        )


class RegionDTOSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source='is_active')
    divisionId = serializers.IntegerField(source='parent_id')

    class Meta:
        model = Shop
        fields = (
            'id',
            'active',
            'divisionId',
            'name',
        )


class DivisionDTOSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source='is_active')

    class Meta:
        model = Shop
        fields = (
            'id',
            'active',
            'name',
        )
