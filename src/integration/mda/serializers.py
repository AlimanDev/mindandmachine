from django.conf import settings
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
    reports = serializers.SerializerMethodField()

    def get_groups(self, user):
        groups = user.position_groups
        if getattr(settings, 'MDA_INTEGRATION_INCLUDE_FUNCTION_GROUPS', False):
            groups += user.function_groups
        return list(set(gr_name for gr_name in groups if gr_name))

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

    def __init__(self, *args, **kwargs):
        super(UserDTOSerializer, self).__init__(*args, **kwargs)
        if getattr(settings, 'MDA_INTEGRATION_TRANSFER_GROUPS_FIELD', False):
            self.fields['groups'] = serializers.SerializerMethodField()
