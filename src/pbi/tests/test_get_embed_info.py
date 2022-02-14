from datetime import datetime, timedelta
from unittest import mock
from uuid import uuid4

import requests
from rest_framework.test import APITestCase

from src.base.tests.factories import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
)
from src.pbi.models import (
    Report,
    ReportPermission,
)
from src.pbi.services.aadservice import AadService
from src.util.mixins.tests import TestsHelperMixin
from src.util.mock import MockResponse


class TestGetEmbedInfo(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.user_dir = UserFactory(email='dir@example.com', network=cls.network)
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='shop',
            network=cls.network,
            email='shop@example.com',
            director=cls.user_dir,
        )
        cls.employee_dir = EmployeeFactory(user=cls.user_dir, tabel_code='dir')
        cls.user_urs = UserFactory(email='urs@example.com', network=cls.network)
        cls.employee_urs = EmployeeFactory(user=cls.user_urs, tabel_code='urs')
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.group_dir = GroupFactory(name='Директор', network=cls.network)
        cls.group_urs = GroupFactory(name='УРС', network=cls.network)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.employment_dir = EmploymentFactory(
            employee=cls.employee_dir, shop=cls.shop, function_group=cls.group_dir,
        )
        cls.employment_urs = EmploymentFactory(
            employee=cls.employee_urs, shop=cls.root_shop, function_group=cls.group_urs,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, function_group=cls.group_worker,
        )
        cls.now = datetime.now() + timedelta(hours=cls.shop.get_tz_offset())
        cls.report_dir = Report.objects.create(
            name='Director report',
            tenant_id=str(uuid4()),
            client_id=str(uuid4()),
            client_secret='client secret',
            workspace_id=str(uuid4()),
            report_id=str(uuid4()),
            use_rls=True,
        )
        cls.report_urs = Report.objects.create(
            name='Urs report',
            tenant_id=str(uuid4()),
            client_id=str(uuid4()),
            client_secret='client secret',
            workspace_id=str(uuid4()),
            report_id=str(uuid4()),
            use_rls=True,
        )
        ReportPermission.objects.create(
            report=cls.report_dir,
            group=cls.group_dir,
        )
        ReportPermission.objects.create(
            report=cls.report_urs,
            group=cls.group_urs,
        )

    def test_receive_report_permission(self):
        report_dir = ReportPermission.get_report_perm(self.user_dir)
        self.assertEqual(self.report_dir.id, report_dir.report_id)

        report_urs = ReportPermission.get_report_perm(self.user_urs)
        self.assertEqual(self.report_urs.id, report_urs.report_id)

        no_report = ReportPermission.get_report_perm(self.user_worker)
        self.assertIsNone(no_report)

        ReportPermission.objects.create(
            report=self.report_dir,
            user=self.user_worker,
        )

        report_dir_by_user = ReportPermission.get_report_perm(self.user_worker)
        self.assertEqual(self.report_dir.id, report_dir_by_user.report_id)

    def test_get_embed_info(self):
        self.client.force_authenticate(user=self.user_urs)
        access_token = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6Ik1yNS1B...'
        with mock.patch.object(AadService, 'get_access_token', return_value=access_token):
            dataset_id = '7b8f2237-b69f-4c2a-9f4c-8f0414279b84'
            requests_get_response = {
                '@odata.context': 'http://wabi-west-europe-e-primary-redirect.analysis.windows.net/v1.0/myorg/groups/dd6fe934-c2f5-42b6-b26b-d732bb3b028d/$metadata#reports/$entity',
                'id': '30ae1b7b-0775-415e-b5d3-2f92a1041d5d', 'reportType': 'PowerBIReport', 'name': 'Test report',
                'webUrl': 'https://app.powerbi.com/groups/dd6fe934-c2f5-42b6-b26b-d732bb3b028d/reports/30ae1b7b-0775-415e-b5d3-2f92a1041d5d',
                'embedUrl': 'https://app.powerbi.com/reportEmbed?reportId=30ae1b7b-0775-415e-b5d3-2f92a1041d5d&groupId=dd6fe934-c2f5-42b6-b26b-d732bb3b028d&w=2&config=eyJjbHVzdGVyVXJsIjoiaHR0cHM6Ly9XQUJJLVdFU1QtRVVST1BFLUUtUFJJTUFSWS1yZWRpcmVjdC5hbmFseXNpcy53aW5kb3dzLm5ldCIsImVtYmVkRmVhdHVyZXMiOnsibW9kZXJuRW1iZWQiOnRydWUsImFuZ3VsYXJPbmx5UmVwb3J0RW1iZWQiOnRydWUsImNlcnRpZmllZFRlbGVtZXRyeUVtYmVkIjp0cnVlLCJ1c2FnZU1ldHJpY3NWTmV4dCI6dHJ1ZSwic2tpcFpvbmVQYXRjaCI6dHJ1ZX19',
                'isFromPbix': False, 'isOwnedByMe': True, 'datasetId': dataset_id,
                'datasetWorkspaceId': 'dd6fe934-c2f5-42b6-b26b-d732bb3b028d', 'users': [], 'subscriptions': []}
            with mock.patch.object(
                    requests, 'get',
                    return_value=MockResponse(json_data=requests_get_response, status_code=200)) as requests_get:
                requests_post_response = {
                    '@odata.context': 'http://wabi-west-europe-e-primary-redirect.analysis.windows.net/v1.0/myorg/$metadata#Microsoft.PowerBI.ServiceContracts.Api.V1.GenerateTokenResponse',
                    'token': 'H4sIAAAAAAAEAB2Ut66EVgBE_-W1WLrkYMnFkllyhu1IS84Zy__uZ_ejKebozN8_VnJ3Y5L__PkTZmVXtICmuSOBtn55TD0HuLebO_DMaByddJ-uyGOXRylpuhIgmTPiXP00j7IKtNFMKlgOCGKZszXbYLQM73TXXeORnkmeB10LsQvbxGgQqsoShpQnq33MdWYhpNJGapR8_slfk5exKvkesrrlV4MgLngCol7vg2tlvW3od0R0d8w-0rKf4KFwiBG5MDjneCW51S0cJYG8hjVyUxleLhcYzixIpLgR68h5XzcwYfmtu_NZjZdXk8IjcDqZCAvcN0z3mRmIhYW3gY7aGs-sWb6yvvhGk0fLu__Bn0cF39Lhxn47jMoSiLtKUtAIuXyU6ywfyEhNJtw6lqdKDh8vo7TqjC2_R9q7YTmlrBJMlBXafK6jx0IyBKMN78zGZa5O4fKbljP_ZYrYkM-DQNAcH2JGkn34tgIqthW4xu4v5EmDJMj3OtextqAZFT9QkRl5JzW0kLDN9ZrV7-H1GRhG0VRzDofRxvd4OdXenqJa1-wvcPJFHmFsJ5dQkvm5KQxGaw8ZmagJdRZZMWMpQvk1IQNph_ahIYiTYFp0drYPVZeCQ7qCMgOse7AqaqlDnoEfrRQ7Wbn4QhYswWNjepYvtZrBEPZ8Ebq8QlDu0kMJvfTMlCshgzLVYANtRPV4csKKFAgyBv4lgo9H4SByTBHrT7LqlCqQ-iJLeywEAORQNBIkhAhZe8NddUE93j9aYMUIhlKfxHtdQCmaREsVtp9erXcdK7Mh9jwi_mZs1QpFaxfYLvP4mdVy54IIGhfPn0Zm7pEiYrQtIetTKaMpl64N-VzBK3udWYh7YvforkTiHdy7YpIQixdvldRTFuqSBMcwyUsu2j9__HDLPW2jWty_OrWs_g0eQscoXqPIRcLAukAxrnrqHn_UXm-wfSdP--K_xwKzqWJqIapsQxsr8pnay3sjVBkFB2CTOijGQ8iISacRNc2hag3p4qgc1RlEvGsDsVmG8ihBKStyd8AX_n3_ktL8hesHqTawy6JYkoM2yZEtLS1edH3bXxQ-uCsee11L9i9wZ5ZOL60JoTN7ryN9snWGYcNuLP14rR99ghadhEv0UqQpw5F4rOuC_k59B1u86GEQrmXNaoZmjqbg9bJ3xvom2jNz3tl-QPyeYnLnWp6JbFgsd6RxRLYQs08MuXWk2xFFu7WeB9QkC7TD6qED5BD69U7cVD3qIsmQ0rwDyWHPr7_--m_me6qKRQl-V7Z79baGLsAu4V1ApAwyYVPL_1NuXQ7Jti_Fb8y_Ee_pTMCuYC4xldB8dul3f3ms6mQ3d5Nngp3Y71n1Z3JrlXtRo9tWUYY5KHf2OIe-JyhTHe5k_QB7qzK14i96N7GRDGKmi1Dz8tCAjyBp4bzLP1bhkk03I5zpkD94vL64tb_HpLiGK0WU9xruSpOjNTBPr-Sq_ngmoj10CzxodpzwG1ZmAxZ303-lp14NFTKYTWRqDZQii3qGaaSdEdWpVJWfn9JXjOGMeaK1AkK1CuyutvVeajeFgXOG9eBWW1b_9mItW2wSH0_6_esJ_Ss1lhgA-Kent8rk7kNm7wh8db_HB6qWa8ZeOV1Xvui-cI9wMkjfE1IyOfu4wG0iwTz9Pxj__As68dNiQgYAAA==.eyJjbHVzdGVyVXJsIjoiaHR0cHM6Ly9XQUJJLVdFU1QtRVVST1BFLUUtUFJJTUFSWS1yZWRpcmVjdC5hbmFseXNpcy53aW5kb3dzLm5ldCIsImVtYmVkRmVhdHVyZXMiOnsibW9kZXJuRW1iZWQiOmZhbHNlfX0=',
                    'tokenId': 'b4cc1558-17b4-4364-83ce-fe6a2285fc7a', 'expiration': '2022-01-27T23:39:23Z'}
                with mock.patch.object(
                        requests, 'post',
                        return_value=MockResponse(json_data=requests_post_response, status_code=200)) as requests_post:
                    resp = self.client.get(self.get_url('get_embed_info'))
                    requests_get.assert_called_once_with(
                        f'https://api.powerbi.com/v1.0/myorg/groups/{self.report_urs.workspace_id}/reports/{self.report_urs.report_id}',
                        headers={
                            'Content-Type': 'application/json',
                            'Authorization': f'Bearer {access_token}',
                        }
                    )
                    requests_post.assert_called_once_with(
                        'https://api.powerbi.com/v1.0/myorg/GenerateToken',
                        data='{"datasets": [{"id": "' + dataset_id + '"}], "reports": [{"id": "' + self.report_urs.report_id + '"}], "targetWorkspaces": [], "identities": [{"username": "' + str(self.user_urs.id) + '", "roles": ["DynamicRlsRole"], "datasets": ["' + dataset_id + '"]}]}',
                        headers={
                            'Content-Type': 'application/json',
                            'Authorization': f'Bearer {access_token}'
                        })
                    resp_data = resp.json()
                    self.assertDictEqual(
                        resp_data,
                        {'tokenId': 'b4cc1558-17b4-4364-83ce-fe6a2285fc7a',
                         'accessToken': 'H4sIAAAAAAAEAB2Ut66EVgBE_-W1WLrkYMnFkllyhu1IS84Zy__uZ_ejKebozN8_VnJ3Y5L__PkTZmVXtICmuSOBtn55TD0HuLebO_DMaByddJ-uyGOXRylpuhIgmTPiXP00j7IKtNFMKlgOCGKZszXbYLQM73TXXeORnkmeB10LsQvbxGgQqsoShpQnq33MdWYhpNJGapR8_slfk5exKvkesrrlV4MgLngCol7vg2tlvW3od0R0d8w-0rKf4KFwiBG5MDjneCW51S0cJYG8hjVyUxleLhcYzixIpLgR68h5XzcwYfmtu_NZjZdXk8IjcDqZCAvcN0z3mRmIhYW3gY7aGs-sWb6yvvhGk0fLu__Bn0cF39Lhxn47jMoSiLtKUtAIuXyU6ywfyEhNJtw6lqdKDh8vo7TqjC2_R9q7YTmlrBJMlBXafK6jx0IyBKMN78zGZa5O4fKbljP_ZYrYkM-DQNAcH2JGkn34tgIqthW4xu4v5EmDJMj3OtextqAZFT9QkRl5JzW0kLDN9ZrV7-H1GRhG0VRzDofRxvd4OdXenqJa1-wvcPJFHmFsJ5dQkvm5KQxGaw8ZmagJdRZZMWMpQvk1IQNph_ahIYiTYFp0drYPVZeCQ7qCMgOse7AqaqlDnoEfrRQ7Wbn4QhYswWNjepYvtZrBEPZ8Ebq8QlDu0kMJvfTMlCshgzLVYANtRPV4csKKFAgyBv4lgo9H4SByTBHrT7LqlCqQ-iJLeywEAORQNBIkhAhZe8NddUE93j9aYMUIhlKfxHtdQCmaREsVtp9erXcdK7Mh9jwi_mZs1QpFaxfYLvP4mdVy54IIGhfPn0Zm7pEiYrQtIetTKaMpl64N-VzBK3udWYh7YvforkTiHdy7YpIQixdvldRTFuqSBMcwyUsu2j9__HDLPW2jWty_OrWs_g0eQscoXqPIRcLAukAxrnrqHn_UXm-wfSdP--K_xwKzqWJqIapsQxsr8pnay3sjVBkFB2CTOijGQ8iISacRNc2hag3p4qgc1RlEvGsDsVmG8ihBKStyd8AX_n3_ktL8hesHqTawy6JYkoM2yZEtLS1edH3bXxQ-uCsee11L9i9wZ5ZOL60JoTN7ryN9snWGYcNuLP14rR99ghadhEv0UqQpw5F4rOuC_k59B1u86GEQrmXNaoZmjqbg9bJ3xvom2jNz3tl-QPyeYnLnWp6JbFgsd6RxRLYQs08MuXWk2xFFu7WeB9QkC7TD6qED5BD69U7cVD3qIsmQ0rwDyWHPr7_--m_me6qKRQl-V7Z79baGLsAu4V1ApAwyYVPL_1NuXQ7Jti_Fb8y_Ee_pTMCuYC4xldB8dul3f3ms6mQ3d5Nngp3Y71n1Z3JrlXtRo9tWUYY5KHf2OIe-JyhTHe5k_QB7qzK14i96N7GRDGKmi1Dz8tCAjyBp4bzLP1bhkk03I5zpkD94vL64tb_HpLiGK0WU9xruSpOjNTBPr-Sq_ngmoj10CzxodpzwG1ZmAxZ303-lp14NFTKYTWRqDZQii3qGaaSdEdWpVJWfn9JXjOGMeaK1AkK1CuyutvVeajeFgXOG9eBWW1b_9mItW2wSH0_6_esJ_Ss1lhgA-Kent8rk7kNm7wh8db_HB6qWa8ZeOV1Xvui-cI9wMkjfE1IyOfu4wG0iwTz9Pxj__As68dNiQgYAAA==.eyJjbHVzdGVyVXJsIjoiaHR0cHM6Ly9XQUJJLVdFU1QtRVVST1BFLUUtUFJJTUFSWS1yZWRpcmVjdC5hbmFseXNpcy53aW5kb3dzLm5ldCIsImVtYmVkRmVhdHVyZXMiOnsibW9kZXJuRW1iZWQiOmZhbHNlfX0=',
                         'tokenExpiry': '2022-01-27T23:39:23Z', 'reportConfig': [
                            {'reportId': '30ae1b7b-0775-415e-b5d3-2f92a1041d5d', 'reportName': 'Test report',
                             'embedUrl': 'https://app.powerbi.com/reportEmbed?reportId=30ae1b7b-0775-415e-b5d3-2f92a1041d5d&groupId=dd6fe934-c2f5-42b6-b26b-d732bb3b028d&w=2&config=eyJjbHVzdGVyVXJsIjoiaHR0cHM6Ly9XQUJJLVdFU1QtRVVST1BFLUUtUFJJTUFSWS1yZWRpcmVjdC5hbmFseXNpcy53aW5kb3dzLm5ldCIsImVtYmVkRmVhdHVyZXMiOnsibW9kZXJuRW1iZWQiOnRydWUsImFuZ3VsYXJPbmx5UmVwb3J0RW1iZWQiOnRydWUsImNlcnRpZmllZFRlbGVtZXRyeUVtYmVkIjp0cnVlLCJ1c2FnZU1ldHJpY3NWTmV4dCI6dHJ1ZSwic2tpcFpvbmVQYXRjaCI6dHJ1ZX19',
                             'datasetId': None}]},
                    )
