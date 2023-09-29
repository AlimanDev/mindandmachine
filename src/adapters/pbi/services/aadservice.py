import msal
from django.conf import settings

# Scope of AAD app. Use the below configuration to use all the permissions provided in the AAD app through Azure portal.
PBI_SCOPE = getattr(settings, 'PBI_SCOPE', ['https://analysis.windows.net/powerbi/api/.default'])
# URL used for initiating authorization request
PBI_AUTHORITY = getattr(settings, 'PBI_AUTHORITY', 'https://login.microsoftonline.com/organizations')


class AadService:
    @staticmethod
    def get_access_token(report_config):
        """Generates and returns Access token
        Returns:
            string: Access token
        """

        try:
            authority = PBI_AUTHORITY.replace('organizations', report_config.tenant_id)
            clientapp = msal.ConfidentialClientApplication(
                report_config.client_id,
                client_credential=report_config.client_secret,
                authority=authority,
            )

            # Make a client call if Access token is not available in cache
            response = clientapp.acquire_token_for_client(scopes=PBI_SCOPE)

            try:
                return response['access_token']
            except KeyError:
                raise Exception(response['error_description'])
        except Exception as ex:
            raise Exception('Error retrieving Access token\n' + str(ex))
