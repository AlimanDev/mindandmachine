import requests
from requests.exceptions import HTTPError
from django.conf import settings

import logging
logger = logging.getLogger('django')


class ZKTeco:
    def get_events(self, page, dt_from=None, dt_to=None, user_id=None,  limit=1000):
        """
        :param page:
        :param dt_from:
        :param dt_to:
        :param user_id:
        :param limit:
        :return:
            {
                "code": 0,
                "message": "success",
                "data": [
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc2",
                        "eventTime": "2020-07-06 14:24:19",
                        "pin": "351",
                        "name": "Евгения",
                        "lastName": "Юдина",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "cardNo": null,
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "eventName": null,
                        "eventPointName": null,
                        "readerName": null,
                        "accZone": "1",
                        "devName": null,
                        "logId": null
                    }, ...
            ]}
        """
        url = 'transaction/listAttTransaction'
        issued=None

        params = {
            'personPin': user_id,
            'pageNo': page,
            'pageSize' : limit,
            'startDate' : dt_from,
            'endDate' : dt_to
        }

        response = self.call('GET', url, params=params)
        return response

    def add_user(self, employment, pin=None, userexternalcode=None):
        department_code = settings.ZKTECO_DEPARTMENT_CODE

        url = 'person/add'

        user = employment.user

        if not pin:
            if userexternalcode:
                pin = userexternalcode.code
            else:
                pin = user.id + 10000

        json = {
            "pin": pin,
            "deptCode": department_code,
            "name": user.first_name,
            "lastName": user.last_name,
            # "gender": "",
            # "birthday": null,
            # "cardNo": null,
            # "supplyCards": null,
            # "personPhoto": null,
            # "selfPwd": "e10adc3949ba59abbe56e057f20f883e",
            # "isSendMail": false,
            # "mobilePhone": "",
            # "personPwd": null,
            # "carPlate": null,
            # "email": null, "ssn": null,
            # "accLevelIds": null,
            # "accStartTime": null, "accEndTime": null,
            # "certType": null, "certNumber": null, "photoPath": null, "hireDate": null
        }

        return self.call('POST', url, json=json)

    def add_personarea(self, userexternalcode, shopexternalcode):
        url = 'attAreaPerson/set' #/?access_token = FB23CAA4B37C348F7D94A54A1774D0338EE91B060F8FDF4227D066CF8100A623
        json = {
            "pins": [userexternalcode.code],
            "code": shopexternalcode.code,
        }
        return self.call('POST', url, json=json)

    def delete_personarea(self, userexternalcode, shopexternalcode):
        url = 'attAreaPerson/delete'
        json = {
            "pins": [userexternalcode.code],
            "code": shopexternalcode.code,
        }
        return self.call('POST', url, json=json)

    def call(self, method, url, data=None, params={}, json=None):
        params.update({'access_token': settings.ZKTECO_KEY})

        response = requests.request(
            method,
            f"{settings.ZKTECO_HOST}/{url}",
            params=params,
            json=json,
            data=data
        )

        try:
            response.raise_for_status()
        except HTTPError as http_err:
            logger.error(http_err)
            raise HTTPError(http_err, response=response)

        return response.json()
