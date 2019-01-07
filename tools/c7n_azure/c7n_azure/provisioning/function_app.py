import os
from binascii import hexlify

from azure.mgmt.web.models import (Site, SiteConfig)

from c7n_azure.utils import azure_name_value_pair

from c7n_azure.provisioning.deployment_unit import DeploymentUnit
from c7n_azure.constants import (FUNCTION_DOCKER_VERSION, FUNCTION_EXT_VERSION)


class FunctionAppDeploymentUnit(DeploymentUnit):

    def __init__(self):
        super(FunctionAppDeploymentUnit, self).__init__(
            'azure.mgmt.web.WebSiteManagementClient')
        self.type = "Function Application"

    def _get(self, params):
        return self.client.web_apps.get(params['resource_group_name'], params['name'])

    def _provision(self, params):
        site_config = SiteConfig(app_settings=[])
        functionapp_def = Site(location=params['location'], site_config=site_config)

        functionapp_def.kind = 'functionapp,linux'
        functionapp_def.server_farm_id = params['app_service_plan_id']

        site_config.linux_fx_version = FUNCTION_DOCKER_VERSION
        site_config.always_on = True

        app_insights_key = params['app_insights_key']
        if app_insights_key:
            site_config.app_settings.append(
                azure_name_value_pair('APPINSIGHTS_INSTRUMENTATIONKEY', app_insights_key))

        con_string = params['storage_account_connection_string']
        site_config.app_settings.append(azure_name_value_pair('AzureWebJobsStorage', con_string))
        site_config.app_settings.append(azure_name_value_pair('AzureWebJobsDashboard', con_string))
        site_config.app_settings.append(azure_name_value_pair('FUNCTIONS_EXTENSION_VERSION',
                                                              FUNCTION_EXT_VERSION))
        site_config.app_settings.append(azure_name_value_pair('FUNCTIONS_WORKER_RUNTIME', 'python'))
        site_config.app_settings.append(
            azure_name_value_pair('MACHINEKEY_DecryptionKey',
                          FunctionAppDeploymentUnit.generate_machine_decryption_key()))

        return self.client.web_apps.create_or_update(params['resource_group_name'],
                                                     params['name'],
                                                     functionapp_def).result()

    @staticmethod
    def generate_machine_decryption_key():
        # randomly generated decryption key for Functions key
        return str(hexlify(os.urandom(32)).decode()).upper()
