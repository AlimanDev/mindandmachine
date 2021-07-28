from rest_framework import serializers

from src.base.models import Shop, User


class ShopDTOSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source='is_active')
    sap = serializers.CharField(source='code')
    locality = serializers.CharField(source='name')
    city = serializers.CharField()
    regionId = serializers.IntegerField(source='parent_id')
    allDay = serializers.BooleanField(source='is_all_day')
    directorLogin = serializers.CharField()
    timeZone = serializers.CharField(source='timezone')

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
            'timeZone',
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


class UserDTOSerializer(serializers.ModelSerializer):
    authType = serializers.CharField(source='upper_auth_type')
    active = serializers.BooleanField()
    orgLevel = serializers.CharField()
    orgUnits = serializers.ListField(child=serializers.CharField())
    position = serializers.CharField()
    admin = serializers.BooleanField()
    supervisor = serializers.BooleanField()
    userChecklistsOrganizer = serializers.BooleanField()
    shopDirector = serializers.BooleanField()
    surveyAdmin = serializers.BooleanField()
    lang = serializers.CharField(source='mda_lang')
    timeZoneId = serializers.CharField()
    # groups = serializers.ListField(child=serializers.CharField())  # пока ничего не передаем
    reports = serializers.SerializerMethodField()

    def get_reports(self, _user):
        return ['REPORT_ALL']

    class Meta:
        model = User
        fields = (
            'id',
            'login',
            'authType',
            'firstName',
            'lastName',
            'email',
            'active',
            'orgLevel',
            'orgUnits',
            'position',
            'admin',
            'supervisor',
            'userChecklistsOrganizer',
            'shopDirector',
            'surveyAdmin',
            'lang',
            # 'password',
            'ldapLogin',
            'timeZoneId',
            'reports',
        )

        extra_kwargs = {
            'login': {
                'source': 'username',
            },
            'firstName': {
                'source': 'first_name',
            },
            'lastName': {
                'source': 'last_name',
            },
            'ldapLogin': {
                'source': 'ldap_login',
            },
        }
