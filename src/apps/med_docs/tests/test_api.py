from rest_framework.test import APITestCase

from src.apps.base.tests import (
    EmploymentFactory,
    GroupFactory,
)
from src.apps.med_docs.models import (
    MedicalDocumentType,
    MedicalDocument,
)
from src.common.mixins.tests import TestsHelperMixin


class TestMedicalDocumentTypeViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group = GroupFactory()
        cls.employment = EmploymentFactory(function_group=cls.admin_group)
        cls.user = cls.employment.employee.user

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user)

    def test_create(self):
        self.add_group_perm(self.admin_group, 'MedicalDocumentType', 'POST')
        create_data = {
            'name': 'Мед. документ 1',
            'code': 'c1',
        }
        resp = self.client.post(
            path=self.get_url('MedicalDocumentType-list'),
            data=self.dump_data(create_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(MedicalDocumentType.objects.count(), 1)

    def test_edit(self):
        self.add_group_perm(self.admin_group, 'MedicalDocumentType', 'PUT')
        med_doc_type = MedicalDocumentType.objects.create(
            name='Мед. док.',
            code='123',
        )
        update_data = {
            'name': 'Новый Мед. документ 1',
            'code': '1234',
        }
        resp = self.client.put(
            path=self.get_url('MedicalDocumentType-detail', pk=med_doc_type.pk),
            data=self.dump_data(update_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        med_doc_type.refresh_from_db()
        self.assertEqual(med_doc_type.name, 'Новый Мед. документ 1')
        self.assertEqual(med_doc_type.code, '1234')

    def test_delete(self):
        self.add_group_perm(self.admin_group, 'MedicalDocumentType', 'DELETE')
        med_doc_type = MedicalDocumentType.objects.create(
            name='Мед. док.',
            code='123',
        )
        resp = self.client.delete(
            path=self.get_url('MedicalDocumentType-detail', pk=med_doc_type.pk),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(MedicalDocumentType.objects.filter(id=med_doc_type.id).exists())

    def test_get_and_list(self):
        self.add_group_perm(self.admin_group, 'MedicalDocumentType', 'GET')
        med_doc_type1 = MedicalDocumentType.objects.create(
            name='Мед. док. 1',
            code='123',
        )
        MedicalDocumentType.objects.create(
            name='Мед. док. 2',
            code='1234',
        )
        resp = self.client.get(
            path=self.get_url('MedicalDocumentType-detail', pk=med_doc_type1.pk),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data, {
            'id': med_doc_type1.id,
            'name': med_doc_type1.name,
            'code': med_doc_type1.code,
        })

        resp = self.client.get(
            path=self.get_url('MedicalDocumentType-list'),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 2)


class TestMedicalDocumentViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group = GroupFactory()
        cls.employment = EmploymentFactory(function_group=cls.admin_group)
        cls.user = cls.employment.employee.user
        cls.med_doc_type = MedicalDocumentType.objects.create(
            name='Мед. док.',
            code='123',
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user)

    def test_create(self):
        self.add_group_perm(self.admin_group, 'MedicalDocument', 'POST')
        create_data = {
            'dt_from': '2021-01-01',
            'dt_to': '2023-01-01',
            'medical_document_type_id': self.med_doc_type.id,
            'employee_id': self.employment.employee_id,
        }
        resp = self.client.post(
            path=self.get_url('MedicalDocument-list'),
            data=self.dump_data(create_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        med_doc = MedicalDocument.objects.first()
        self.assertIsNotNone(med_doc)
        resp_data = resp.json()
        self.assertDictEqual(
            {
                'id': med_doc.id,
                'dt_from': '2021-01-01',
                'dt_to': '2023-01-01',
                'medical_document_type_id': self.med_doc_type.id,
                'employee_id': self.employment.employee_id,
            },
            resp_data,
        )

    def test_edit(self):
        self.add_group_perm(self.admin_group, 'MedicalDocument', 'PUT')
        med_doc = MedicalDocument.objects.create(
            medical_document_type=self.med_doc_type,
            employee=self.employment.employee,
            dt_from='2021-01-01',
            dt_to='2024-01-01',
        )
        update_data = {
            'medical_document_type_id': self.med_doc_type.id,
            'employee_id': self.employment.employee_id,
            'dt_from': '2021-01-01',
            'dt_to': '2025-01-01',
        }
        resp = self.client.put(
            path=self.get_url('MedicalDocument-detail', pk=med_doc.pk),
            data=self.dump_data(update_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        med_doc.refresh_from_db()
        self.assertEqual(med_doc.dt_to.strftime('%Y-%m-%d'), '2025-01-01')

    def test_delete(self):
        self.add_group_perm(self.admin_group, 'MedicalDocument', 'DELETE')
        med_doc = MedicalDocument.objects.create(
            medical_document_type=self.med_doc_type,
            employee=self.employment.employee,
            dt_from='2021-01-01',
            dt_to='2024-01-01',
        )
        resp = self.client.delete(
            path=self.get_url('MedicalDocument-detail', pk=med_doc.pk),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(MedicalDocumentType.objects.filter(id=med_doc.id).exists())

    def test_get_and_list(self):
        self.add_group_perm(self.admin_group, 'MedicalDocument', 'GET')
        med_doc = MedicalDocument.objects.create(
            medical_document_type=self.med_doc_type,
            employee=self.employment.employee,
            dt_from='2021-01-01',
            dt_to='2024-01-01',
        )
        resp = self.client.get(
            path=self.get_url('MedicalDocument-detail', pk=med_doc.pk),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data, {
            'id': med_doc.id,
            'medical_document_type_id': self.med_doc_type.id,
            'employee_id': self.employment.employee_id,
            'dt_from': '2021-01-01',
            'dt_to': '2024-01-01',
        })

        resp = self.client.get(
            path=self.get_url('MedicalDocument-list'),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        resp = self.client.get(
            path=self.get_url('MedicalDocument-list'),
            data={'employee_id': self.employment.employee_id + 1}
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 0)
