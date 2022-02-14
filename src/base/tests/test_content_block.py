from rest_framework.test import APITestCase
from src.util.mixins.tests import TestsHelperMixin
from src.base.models import ContentBlock

class TestContentBlock(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_get_content_block(self):
        content_block = ContentBlock.objects.create(
            code='support_modal_text',
            network=self.network,
            name='Обратная связь',
            body=('<p>Напишите о проблеме нам на почту <a href="mailto:support@mindandmachine.ru">support@mindandmachine.ru</a>.'
            '<br> Расскажите о ней подробно:'
            '<ul style="margin: 0;">'
            '<li>дату и время проблемы,</li>'
            '<li>какие действия привели к проблеме.</li></ul>'
            'Обязательно укажите название торговой точки. Если проблема касается конкретных сотрудников, то укажите их ФИО и должность.'
            '<br> Желательно сделать скриншот (снимок экрана) проблемы и приложить его к вашему запросу.</p>'),
        )
        second_content_block = ContentBlock.objects.create(
            code='second_block',
            network=self.network,
            name='Second block name',
            body='Second block body',
        )
        response = self.client.get(f"{self.get_url('ContentBlock-list')}?code=support_modal_text")
        resp = response.json()
        self.assertEqual(len(resp), 1)
        self.assertEqual(resp[0]['code'], content_block.code)
        self.assertEqual(
            resp[0]['body'], 
            ('<p>Напишите о проблеме нам на почту <a href="mailto:support@mindandmachine.ru">support@mindandmachine.ru</a>.'
            '<br> Расскажите о ней подробно:'
            '<ul style="margin: 0;">'
            '<li>дату и время проблемы,</li>'
            '<li>какие действия привели к проблеме.</li></ul>'
            'Обязательно укажите название торговой точки. Если проблема касается конкретных сотрудников, то укажите их ФИО и должность.'
            '<br> Желательно сделать скриншот (снимок экрана) проблемы и приложить его к вашему запросу.</p>')
        )
