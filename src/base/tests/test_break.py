from rest_framework.test import APITestCase
from src.base.models import Break
from src.util.mixins.tests import TestsHelperMixin
from rest_framework.serializers import ValidationError


class TestBreakValidation(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_success_create(self):
        breaks = Break.objects.create(
            network=self.network,
            name='Перерыв',
            value='[[0, 100, [30]], [101, 200, [40]]]',
        )

        self.assertEqual(breaks.breaks, [[0, 100, [30]], [101, 200, [40]]])

    def test_create_with_bad_type(self):
        b = None
        # некорректная длина
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[[0, 100, [30]], [101, 200]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Некорректный формат перерыва [101, 200], должно быть [[int, int, [int, int,]],].'])

        self.assertIsNone(b)
        
        # некорректный тип перерыва
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[[0, 100, [30]], [101, 200, 300]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Некорректный формат перерыва [101, 200, 300], должно быть [[int, int, [int, int,]],].'])

        self.assertIsNone(b)

        # некорректный тип интервала
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[[0, 100, [30]], ["101", 200, [40]]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Некорректный формат перерыва [\'101\', 200, [40]], должно быть [[int, int, [int, int,]],].'])

        self.assertIsNone(b)

        # некорректный тип перерыва
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[[0, 100, [30]], [101, 200, [40, "10"]]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Некорректный формат перерыва [101, 200, [40, \'10\']], должно быть [[int, int, [int, int,]],].'])

        self.assertIsNone(b)

        # некорректный формат
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[0, 100, [30]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Некорректный формат перерыва 0, должно быть [[int, int, [int, int,]],].'])

        self.assertIsNone(b)

    def test_bad_periods(self):
        b = None
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[[0, 100, [30]], [200, 101, [40]]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Первое значение периода не может быть больше второго значения: [200, 101, [40]]'])

        self.assertIsNone(b)

    def test_bad_value(self):
        b = None
        try:
            b = Break.objects.create(
                network=self.network,
                name='Перерыв',
                value='[[0, 100, [30]], [101, 200, [300]]]',
            )
        except ValidationError as e:
            self.assertEqual(e.detail, ['Значение перерыва не может быть больше значения периода: [101, 200, [300]]'])

        self.assertIsNone(b)
