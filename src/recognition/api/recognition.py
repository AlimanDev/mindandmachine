"""
Использование:

recognition = Recognition()
database_id = recognition.create_database(some_dict)
person_id = recognition.create_person(some_dict)
photo_id = recognition.upload_photo(person_id, image)
user_id = recognition.identify(image)

Документация по апи:
https://docs.facecloud.tevian.ru/#/user/post_api_v1_users
"""
import logging

import requests
from django.conf import settings
from requests.exceptions import HTTPError

logger = logging.getLogger('django')

TEVIAN_URL = settings.TEVIAN_URL
TEVIAN_EMAIL = settings.TEVIAN_EMAIL
TEVIAN_PASSWORD = settings.TEVIAN_PASSWORD
TEVIAN_DATABASE_ID = settings.TEVIAN_DATABASE_ID
TEVIAN_FD_THRESHOLD = settings.TEVIAN_FD_THRESHOLD
TEVIAN_FR_THRESHOLD = settings.TEVIAN_FR_THRESHOLD


class Recognition:
    _partner = None

    @property
    def partner(self):
        if self._partner is None:
            self._partner = globals()[settings.RECOGNITION_PARTNER]()

        return self._partner

    def create_database(self, data):
        return self.partner.create_database(data)

    def create_person(self, data):
        return self.partner.create_person(data)

    def upload_photo(self, id, image):
        return self.partner.upload_photo(id, image)

    def identify(self, image):
        return self.partner.identify(image)

    def match(self, partner_id, image):
        return self.partner.match(partner_id, image)

    def detect(self, image):
        return self.partner.detect(image)

    def detect_and_match(self, partner_id, image):
        return self.partner.detect_and_match(partner_id, image)

    def delete_person(self, partner_id):
        return self.partner.delete_person(partner_id)


class Tevian:
    def __init__(self):
        self.login()
        self.database_id = TEVIAN_DATABASE_ID

    def login(self):
        response = self._call(
            'POST',
            TEVIAN_URL + "login",
            json={
                "email": TEVIAN_EMAIL,
                "password": TEVIAN_PASSWORD,
            },
            auth=False
        )
        self.token = response['access_token']

    def authenticate(request):
        def relogin(self, *args, **kwargs):
            try:
                result = request(self, *args, **kwargs)
            except HTTPError as http_err:
                if http_err.response.status_code == 401:
                    self.login()
                    result = request(self, *args, **kwargs)
                else:
                    raise (http_err)
            return result

        return relogin

    @authenticate
    def detect_and_match(self, tevian_id, image):
        """
            image: binary filehandler, only django.core.files.InMemoryUploadedFile
             because filehandler should be read multiple times
            returns:
                    {'liveness': 0.999423,
                    'score': 0.999423}
        """
        detect = self.detect(image)
        if not detect:
            return {'liveness': 0,
                    'score': 0}
        detect = detect[0]
        bbox = detect['bbox']
        pos_names = ['x', 'y', 'width', 'height']

        face_pos = ','.join([
            str(bbox[k]) for k in pos_names])
        match = self.match(
            tevian_id,
            image,
            params={'face': face_pos}
        )
        score = match['score'] if match and 'score' in match else 0

        return {'liveness': detect['liveness'],
                'score': score}

    @authenticate
    def match(self, tevian_id, image, params=None):
        """
            image: binary filehandler
            returns on success:
                {'face': {'bbox': {'height': 465, 'width': 465, 'x': 349, 'y': 494},
                'score': 0.999423},
                'photo': {'id': 926},
                'score': 1.0}
            returns on failure: None


        """
        return self._call(
            'POST',
            f"{TEVIAN_URL}persons/{tevian_id}/match",
            data=image,
            params=params,
            headers={'Content-Type': 'image/jpeg'}
        )

    @authenticate
    def detect(self, image):
        """
            image: binary filehandler
            returns on success: [{'bbox': {'height': 256, 'width': 256, 'x': 176, 'y': 176},
                      'liveness': 0.999812,
                      'score': 0.999763}]
            returns None if no face detected


        """
        return self._call(
            'POST',
            f"{TEVIAN_URL}detect",
            params={"liveness": 1},
            data=image,
            headers={'Content-Type': 'image/jpeg'}
        )

    @authenticate
    def create_database(self, data):
        """
            data: some db informaion
            returns: tevian database id
        """
        res = self._call(
            'POST',
            TEVIAN_URL + "databases",
            json={
                "data": data,
            },
        )
        return res['id']

    @authenticate
    def create_person(self, data):
        """
            data: QoS user info
            returns: tevian id
        """
        res = self._call(
            'POST',
            TEVIAN_URL + "persons",
            json={
                "data": data,
                "database_id": self.database_id
            },
        )
        return res['id']

    @authenticate
    def delete_person(self, tevian_id):
        return self._call(
            'DELETE',
            TEVIAN_URL + "persons/" + str(tevian_id),
        )

    @authenticate
    def upload_photo(self, tevian_id, image):
        """
            image: binary filehandler
            returns: photo_id
        """
        res = self._call(
            'POST',
            TEVIAN_URL + 'photos',
            params={"fd_min_size": 0,
                    "fd_max_size": 0,
                    "fd_threshold": 0.2,
                    "person_id": tevian_id,
                    },
            data=image,
            headers={'Content-Type': 'image/jpeg'}
        )
        return res['id']

    @authenticate
    def delete_photo(self, photo_id):
        return self._call(
            'DELETE',
            TEVIAN_URL + "photos/" + str(photo_id),
        )

    @authenticate
    def identify(self, image):
        """
            image: binary filehandler
            returns: tevian_id
        """
        res = self._call(
            'POST',
            f"{TEVIAN_URL}databases/{self.database_id}/identify",
            params={
                "fr_threshold": TEVIAN_FR_THRESHOLD,
                "fd_min_size": 0,
                "fd_max_size": 0,
                "fd_threshold": TEVIAN_FD_THRESHOLD,
                "fr_rank": 1
            },
            data=image,
            headers={'Content-Type': 'image/jpeg'}
        )
        matches = res['matches']
        if len(matches):
            return matches[0]['person']['id']

    @authenticate
    def create_demo_account(self, email, password, data):
        """
            data: QoS user info
            returns: tevian user id
        """
        res = self._call(
            'POST',
            TEVIAN_URL + "users",
            json={
                "data": data,
                "email": email,
                "password": password
            },
        )
        return res['id']

    def _call(self, method, url, json=None, data=None, params=None, headers=None, auth=True):
        # try:

        logger.debug("Recognition call {} {}".format(url, params))
        if auth:
            if not headers:
                headers = {}
            if self.token:
                headers['Authorization'] = f"Bearer {self.token}"

        response = requests.request(
            method,
            url,
            data=data,
            json=json,
            params=params,
            headers=headers
        )

        try:
            response.raise_for_status()
        except HTTPError as http_err:
            message = http_err.response.json()['message']
            logger.error(http_err, http_err.response.json()['message'])
            raise HTTPError(message, response=response)
        # except Exception as err:
        #     print(f'Some error occurred: {err}')
        # else:
        res = response.json()
        if 'data' in res:
            return res['data']

        logger.warn("Recognition error message {} for url {} {}".format(res, url, params))
        return None
