from rest_framework.reverse import reverse
from rest_framework.test import APIClient, APITestCase
from src.base.tests.factories import ShopFactory, UserFactory, NetworkFactory, GroupFactory
from src.recognition.models import ShopIpAddress
from src.util.mixins.tests import TestsHelperMixin


class TestShopIpAddress(TestsHelperMixin, APITestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("ShopIpAddress-list")
        cls.network = NetworkFactory()
        cls.create_departments_and_users()
        cls.ips = ["209.5.0.99", "146.143.220.29", "124.231.233.50", '25.125.87.118', "73.250.141.137",
                    "214.131.174.61", "141.13.246.105", "238.3.75.196", "182.105.201.47", "147.243.52.8"]
        for ip in cls.ips:
            ShopIpAddress.objects.create(shop=cls.shop, ip_address=ip)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user1)

    def test_get_shop_ip_address_api(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), len(self.ips))

    def test_create_shop_ip_address_api(self):
        data = {
            'shop': self.shop.id,
            'ip_address': '111.111.222.0'
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['ip_address'], data['ip_address'])

    def test_delete_shop_ip_address_api(self):
        ip_addr = ShopIpAddress.objects.get(ip_address='147.243.52.8')
        remove_url = reverse("ShopIpAddress-detail", args=[ip_addr.id])
        response = self.client.delete(remove_url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ShopIpAddress.objects.all().count(), 9)

