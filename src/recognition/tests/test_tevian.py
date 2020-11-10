import unittest

from src.recognition.api.recognition import Tevian


class TestTevian(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.tevian = Tevian()

    def test_api(self):
        person_id = self.tevian.create_person({"test": "test"})
        self.assertEqual(type(person_id), int, 'no person created')

        i = open('src/recognition/test_data/1.jpg', 'rb')
        photo_id = self.tevian.upload_photo(person_id, i)
        self.assertEqual(type(photo_id), int, 'no photo created')

        i = open('src/recognition/test_data/2.jpg', 'rb')
        match = self.tevian.match(person_id, i)
        self.assertTrue('score' in match, 'true pic didn\'t matched')
        #
        # i = open('recognition/test_data/1_fake.jpg','rb')
        # match = self.tevian.match(person_id, i)
        # self.assertFalse(match, 'black white pic matched')

        i = open('src/recognition/test_data/2_fake.jpg', 'rb')
        match = self.tevian.match(person_id, i)
        self.assertFalse(match, 'wrong pic matched')

        i = open('src/recognition/test_data/1.jpg', 'rb', buffering=0)
        detect = self.tevian.detect(i)[0]
        self.assertTrue(detect['liveness'] > 0 and detect['score'] > 0, 'detect failed')
