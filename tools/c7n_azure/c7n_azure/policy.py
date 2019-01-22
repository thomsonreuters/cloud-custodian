# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import re
import sys

import six
from azure.mgmt.eventgrid.models import \
    StorageQueueEventSubscriptionDestination, StringInAdvancedFilter, EventSubscriptionFilter

from c7n import utils
from c7n.actions import EventAction
from c7n.policy import PullMode, ServerlessExecutionMode, execution
from c7n.utils import local_session
from c7n_azure.azure_events import AzureEvents, AzureEventSubscription
from c7n_azure.constants import (FUNCTION_EVENT_TRIGGER_MODE,
                                 FUNCTION_TIME_TRIGGER_MODE)
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ResourceIdParser, StringUtils


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'appInsights': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string'}
                         }
                    ]
                },
                'storageAccount': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string'}
                         }
                    ]
                },
                'servicePlan': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string',
                             'skuTier': 'string',
                             'skuName': 'string'}
                         }
                    ]
                },
            },
            'execution-options': {'type': 'object'}
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    default_storage_name = "custodian"

    def __init__(self, policy):

        self.policy = policy
        self.log = logging.getLogger('custodian.azure.AzureFunctionMode')
        self.policy_name = self.policy.data['name'].replace(' ', '-').lower()
        self.function_params = None
        self.function_app = None

    def get_function_app_params(self):
        session = local_session(self.policy.session_factory)

        provision_options = self.policy.data['mode'].get('provision-options', {})

        # Service plan is parsed first, location might be shared with storage & insights
        service_plan = AzureFunctionMode.extract_properties(
            provision_options,
            'servicePlan',
            {
                'name': 'cloud-custodian',
                'location': 'eastus',
                'resource_group_name': 'cloud-custodian',
                'sku_tier': 'Dynamic',  # consumption plan
                'sku_name': 'Y1'
            })

        # Metadata used for automatic naming
        location = service_plan.get('location', 'eastus')
        rg_name = service_plan['resource_group_name']
        sub_id = session.get_subscription_id()
        target_sub_id = session.get_function_target_subscription_id()
        function_suffix = StringUtils.naming_hash(rg_name + target_sub_id)
        storage_suffix = StringUtils.naming_hash(rg_name + sub_id)

        storage_account = AzureFunctionMode.extract_properties(
            provision_options,
            'storageAccount',
            {
                'name': self.default_storage_name + storage_suffix,
                'location': location,
                'resource_group_name': rg_name
            })

        app_insights = AzureFunctionMode.extract_properties(
            provision_options,
            'appInsights',
            {
                'name': service_plan['name'],
                'location': location,
                'resource_group_name': rg_name
            })

        function_app_name = FunctionAppUtilities.get_function_name(self.policy_name,
            function_suffix)
        FunctionAppUtilities.validate_function_name(function_app_name)

        params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights=app_insights,
            service_plan=service_plan,
            storage_account=storage_account,
            function_app_resource_group_name=service_plan['resource_group_name'],
            function_app_name=function_app_name)

        return params

    @staticmethod
    def extract_properties(options, name, properties):
        settings = options.get(name, {})
        result = {}
        # str type implies settings is a resource id
        if isinstance(settings, six.string_types):
            result['id'] = settings
            result['name'] = ResourceIdParser.get_resource_name(settings)
            result['resource_group_name'] = ResourceIdParser.get_resource_group(settings)
        else:
            for key in properties.keys():
                result[key] = settings.get(StringUtils.snake_to_camel(key), properties[key])

        return result

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        # Make sure we have auth data for function provisioning
        session = local_session(self.policy.session_factory)
        session.get_functions_auth_string()

        if sys.version_info[0] < 3:
            self.log.error("Python 2.7 is not supported for deploying Azure Functions.")
            sys.exit(1)

        self.function_params = self.get_function_app_params()
        self.function_app = FunctionAppUtilities.deploy_function_app(self.function_params)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def build_functions_package(self, queue_name=None):
        self.log.info("Building function package for %s" % self.function_params.function_app_name)

        package = FunctionPackage(self.policy_name)
        package.build(self.policy.data,
                      modules=['c7n', 'c7n-azure', 'applicationinsights'],
                      non_binary_packages=['pyyaml', 'pycparser', 'tabulate'],
                      excluded_packages=['azure-cli-core', 'distlib', 'futures'],
                      queue_name=queue_name)
        package.close()

        self.log.info("Function package built, size is %dMB" % (package.pkg.size / (1024 * 1024)))
        return package


@execution.register(FUNCTION_TIME_TRIGGER_MODE)
class AzurePeriodicMode(AzureFunctionMode, PullMode):
    """A policy that runs/execute s in azure functions at specified
    time intervals."""
    schema = utils.type_schema(FUNCTION_TIME_TRIGGER_MODE,
                               schedule={'type': 'string'},
                               rinherit=AzureFunctionMode.schema)

    def provision(self):
        super(AzurePeriodicMode, self).provision()
        package = self.build_functions_package()
        FunctionAppUtilities.publish_functions_package(self.function_params, package)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return PullMode.run(self)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")


@execution.register(FUNCTION_EVENT_TRIGGER_MODE)
class AzureEventGridMode(AzureFunctionMode):
    """A policy that runs/executes in azure functions from an
    azure event."""

    schema = utils.type_schema(FUNCTION_EVENT_TRIGGER_MODE,
                               events={'type': 'array', 'items': {
                                   'oneOf': [
                                       {'type': 'string'},
                                       {'type': 'object',
                                        'required': ['resourceProvider', 'event'],
                                        'properties': {
                                            'resourceProvider': {'type': 'string'},
                                            'event': {'type': 'string'}}}]
                               }},
                               required=['events'],
                               rinherit=AzureFunctionMode.schema)

    def provision(self):
        super(AzureEventGridMode, self).provision()
        session = local_session(self.policy.session_factory)

        # queue name is restricted to lowercase letters, numbers, and single hyphens
        queue_name = re.sub(r'(-{2,})+', '-', self.function_params.function_app_name.lower())
        storage_account = self._create_storage_queue(queue_name, session)
        self._create_event_subscription(storage_account, queue_name, session)
        package = self.build_functions_package(queue_name)
        FunctionAppUtilities.publish_functions_package(self.function_params, package)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        resources = self.policy.resource_manager.get_resources([event['subject']])

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        if not resources:
            self.policy.log.info(
                "policy: %s resources: %s no resources found" % (
                    self.policy.name, self.policy.resource_type))
            return

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        with self.policy.ctx:
            self.policy.ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy",
                buffer=False)

            self.policy._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            for action in self.policy.resource_manager.actions:
                self.policy.log.info(
                    "policy: %s invoking action: %s resources: %d",
                    self.policy.name, action.name, len(resources))
                if isinstance(action, EventAction):
                    results = action.process(resources, event)
                else:
                    results = action.process(resources)
                self.policy._write_file(
                    "action-%s" % action.name, utils.dumps(results))

        return resources

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")

    def _create_storage_queue(self, queue_name, session):
        self.log.info("Creating storage queue")
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
        storage_account = storage_client.storage_accounts.get_properties(
            self.function_params.storage_account['resource_group_name'],
            self.function_params.storage_account['name'])

        try:
            StorageUtilities.create_queue_from_storage_account(storage_account, queue_name, session)
            self.log.info("Storage queue creation succeeded")
            return storage_account
        except Exception as e:
            self.log.error('Queue creation failed with error: %s' % e)
            raise SystemExit

    def _create_event_subscription(self, storage_account, queue_name, session):
        self.log.info('Creating event grid subscription')
        destination = StorageQueueEventSubscriptionDestination(resource_id=storage_account.id,
                                                               queue_name=queue_name)

        # filter specific events
        subscribed_events = AzureEvents.get_event_operations(
            self.policy.data['mode'].get('events'))
        advance_filter = StringInAdvancedFilter(key='Data.OperationName', values=subscribed_events)
        event_filter = EventSubscriptionFilter(advanced_filters=[advance_filter])

        try:
            AzureEventSubscription.create(destination, queue_name, session, event_filter)
            self.log.info('Event grid subscription creation succeeded')
        except Exception as e:
            self.log.error('Event Subscription creation failed with error: %s' % e)
            raise SystemExit
