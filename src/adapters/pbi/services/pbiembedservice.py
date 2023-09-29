import json

import requests

from src.adapters.pbi.entities.embedconfig import EmbedConfig
from src.adapters.pbi.entities.embedtoken import EmbedToken
from src.adapters.pbi.entities.embedtokenrequestbody import EmbedTokenRequestBody
from src.adapters.pbi.entities.reportconfig import ReportConfig
from src.adapters.pbi.services.aadservice import AadService
from django.conf import settings


PBI_DYNAMIC_RLS_ROLE_NAME = getattr(settings, 'PBI_DYNAMIC_RLS_ROLE_NAME', 'DynamicRlsRole')


class PbiEmbedServiceException(Exception):
    pass


class PbiEmbedService:
    def __init__(self, report_config, user_id=None):
        self.report_config = report_config
        self.user_id = user_id

    def get_embed_params_for_single_report(self):
        '''Get embed params for a report and a workspace

        Args:
            workspace_id (str): Workspace Id
            report_id (str): Report Id
            additional_dataset_id (str, optional): Dataset Id different than the one bound to the report. Defaults to None.

        Returns:
            EmbedConfig: Embed token and Embed URL
        '''

        report_url = f'https://api.powerbi.com/v1.0/myorg/groups/{self.report_config.workspace_id}/reports/{self.report_config.report_id}'
        api_response = requests.get(report_url, headers=self.get_request_header(), timeout=settings.REQUESTS_TIMEOUTS['pbi_embed_service'])

        if api_response.status_code != 200:
            raise PbiEmbedServiceException(
                f'Error while retrieving Embed URL\n{api_response.reason}:\t{api_response.text}\nRequestId:\t{api_response.headers.get("RequestId")}')

        api_response = api_response.json()
        report = ReportConfig(api_response['id'], api_response['name'], api_response['embedUrl'])
        dataset_ids = [api_response['datasetId']]

        embed_token = self.get_embed_token_for_single_report_single_workspace(dataset_ids)
        embed_config = EmbedConfig(embed_token.tokenId, embed_token.token, embed_token.tokenExpiry, [report.__dict__])
        return embed_config.__dict__

    def get_embed_token_for_single_report_single_workspace(self, dataset_ids):
        '''Get Embed token for single report, multiple datasets, and an optional target workspace

        Args:
            report_id (str): Report Id
            dataset_ids (list): Dataset Ids
            target_workspace_id (str, optional): Workspace Id. Defaults to None.
            identities (list, optional): The list of identities to use for row-level security rules

        Returns:
            EmbedToken: Embed token
        '''

        request_body = EmbedTokenRequestBody()

        for dataset_id in dataset_ids:
            request_body.datasets.append({'id': dataset_id})
            if self.user_id:
                if not hasattr(request_body, 'identities'):
                    request_body.identities = []

                request_body.identities.append({
                    'username': str(self.user_id),
                    'roles': [
                        PBI_DYNAMIC_RLS_ROLE_NAME,
                    ],
                    'datasets': [
                        dataset_id
                    ]
                })

        request_body.reports.append({'id': self.report_config.report_id})

        # Generate Embed token for multiple workspaces, datasets, and reports. Refer https://aka.ms/MultiResourceEmbedToken
        embed_token_api = 'https://api.powerbi.com/v1.0/myorg/GenerateToken'
        api_response = requests.post(embed_token_api, data=json.dumps(request_body.__dict__),
                                     headers=self.get_request_header(), timeout=settings.REQUESTS_TIMEOUTS['pbi_embed_service'])

        if api_response.status_code != 200:
            raise PbiEmbedServiceException(
                f'Error while retrieving Embed token\n{api_response.reason}:\t{api_response.text}\nRequestId:\t{api_response.headers.get("RequestId")}')

        api_response = api_response.json()
        embed_token = EmbedToken(api_response['tokenId'], api_response['token'], api_response['expiration'])
        return embed_token

    def get_request_header(self):
        '''Get Power BI API request header

        Returns:
            Dict: Request header
        '''
        return {'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + AadService.get_access_token(self.report_config)}
