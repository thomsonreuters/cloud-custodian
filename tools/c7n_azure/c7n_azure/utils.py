# Copyright 2018 Capital One Services, LLC
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
import collections
import datetime
import hashlib
import logging
import re
import time
import uuid
from builtins import bytes
from concurrent.futures import as_completed

import six
from azure.graphrbac.models import GetObjectsParameters, DirectoryObject
from azure.mgmt.web.models import NameValuePair
from c7n_azure import constants
from msrestazure.azure_exceptions import CloudError
from msrestazure.tools import parse_resource_id

from c7n.utils import chunks

from c7n.utils import local_session


class ResourceIdParser(object):

    @staticmethod
    def get_namespace(resource_id):
        return parse_resource_id(resource_id).get('namespace')

    @staticmethod
    def get_resource_group(resource_id):
        result = parse_resource_id(resource_id).get("resource_group")
        # parse_resource_id fails to parse resource id for resource groups
        if result is None:
            return resource_id.split('/')[4]
        return result

    @staticmethod
    def get_resource_type(resource_id):
        parsed = parse_resource_id(resource_id)
        # parse_resource_id returns dictionary with "child_type_#" to represent
        # types sequence. "type" stores root type.
        child_type_keys = [k for k in parsed.keys() if k.find("child_type_") != -1]
        types = [parsed.get(k) for k in sorted(child_type_keys)]
        types.insert(0, parsed.get('type'))
        return '/'.join(types)

    @staticmethod
    def get_resource_name(resource_id):
        return parse_resource_id(resource_id).get('resource_name')


class StringUtils(object):

    @staticmethod
    def equal(a, b, case_insensitive=True):
        if isinstance(a, six.string_types) and isinstance(b, six.string_types):
            if case_insensitive:
                return a.strip().lower() == b.strip().lower()
            else:
                return a.strip() == b.strip()

        return False

    @staticmethod
    def snake_to_camel(string):
        components = string.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])

    @staticmethod
    def naming_hash(string, length=8):
        return hashlib.sha256(bytes(string, 'utf-8')).hexdigest().lower()[:length]


def utcnow():
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.utcnow()


def now(tz=None):
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.now(tz=tz)


def azure_name_value_pair(name, value):
    return NameValuePair(**{'name': name, 'value': value})


send_logger = logging.getLogger('custodian.azure.utils.ServiceClient.send')


def custodian_azure_send_override(self, request, headers=None, content=None, **kwargs):
    """ Overrides ServiceClient.send() function to implement retries & log headers
    """
    retries = 0
    max_retries = 3
    while retries < max_retries:
        response = self.orig_send(request, headers, content, **kwargs)

        send_logger.debug(response.status_code)
        for k, v in response.headers.items():
            if k.startswith('x-ms-ratelimit'):
                send_logger.debug(k + ':' + v)

        # Retry codes from urllib3/util/retry.py
        if response.status_code in [413, 429, 503]:
            retry_after = None
            for k in response.headers.keys():
                if StringUtils.equal('retry-after', k):
                    retry_after = int(response.headers[k])

            if retry_after is not None and retry_after < constants.DEFAULT_MAX_RETRY_AFTER:
                send_logger.warning('Received retriable error code %i. Retry-After: %i'
                                    % (response.status_code, retry_after))
                time.sleep(retry_after)
                retries += 1
            else:
                send_logger.error("Received throttling error, retry time is %i"
                                  "(retry only if < %i seconds)."
                                  % (retry_after, constants.DEFAULT_MAX_RETRY_AFTER))
                break
        else:
            break
    return response


class ThreadHelper:

    disable_multi_threading = False

    @staticmethod
    def execute_in_parallel(resources, event, execution_method, executor_factory, log,
                            max_workers=constants.DEFAULT_MAX_THREAD_WORKERS,
                            chunk_size=constants.DEFAULT_CHUNK_SIZE):
        futures = []
        results = []
        exceptions = []

        if ThreadHelper.disable_multi_threading:
            try:
                result = execution_method(resources, event)
                if result:
                    results.extend(result)
            except Exception as e:
                exceptions.append(e)
        else:
            with executor_factory(max_workers=max_workers) as w:
                for resource_set in chunks(resources, chunk_size):
                    futures.append(w.submit(execution_method, resource_set, event))

                for f in as_completed(futures):
                    if f.exception():
                        log.error(
                            "Execution failed with error: %s" % f.exception())
                        exceptions.append(f.exception())
                    else:
                        result = f.result()
                        if result:
                            results.extend(result)

        return results, list(set(exceptions))


class Math(object):

    @staticmethod
    def mean(numbers):
        clean_numbers = [e for e in numbers if e is not None]
        return float(sum(clean_numbers)) / max(len(clean_numbers), 1)

    @staticmethod
    def sum(numbers):
        clean_numbers = [e for e in numbers if e is not None]
        return float(sum(clean_numbers))


class GraphHelper(object):
    log = logging.getLogger('custodian.azure.utils.GraphHelper')

    @staticmethod
    def get_principal_dictionary(graph_client, object_ids):
        object_params = GetObjectsParameters(
            include_directory_object_references=True,
            object_ids=object_ids)

        principal_dics = {object_id: DirectoryObject() for object_id in object_ids}

        aad_objects = graph_client.objects.get_objects_by_object_ids(object_params)
        try:
            for aad_object in aad_objects:
                principal_dics[aad_object.object_id] = aad_object
        except CloudError:
            GraphHelper.log.warning(
                'Credentials not authorized for access to read from Microsoft Graph. \n '
                'Can not query on principalName, displayName, or aadType. \n')

        return principal_dics

    @staticmethod
    def get_principal_name(graph_object):
        if hasattr(graph_object, 'user_principal_name'):
            return graph_object.user_principal_name
        elif hasattr(graph_object, 'service_principal_names'):
            return graph_object.service_principal_names[0]
        elif hasattr(graph_object, 'display_name'):
            return graph_object.display_name
        return ''


class PortsRangeHelper(object):

    PortsRange = collections.namedtuple('PortsRange', 'start end')

    @staticmethod
    def _get_port_range(range_str):
        """ Given a string with a port or port range: '80', '80-120'
            Returns tuple with range start and end ports: (80, 80), (80, 120)
        """
        if range_str == '*':
            return PortsRangeHelper.PortsRange(start=0, end=65535)

        s = range_str.split('-')
        if len(s) == 2:
            return PortsRangeHelper.PortsRange(start=int(s[0]), end=int(s[1]))

        return PortsRangeHelper.PortsRange(start=int(s[0]), end=int(s[0]))

    @staticmethod
    def _get_string_port_ranges(ports):
        """ Extracts ports ranges from the string
            Returns an array of PortsRange tuples
        """
        return [PortsRangeHelper._get_port_range(r) for r in ports.split(',') if r != '']

    @staticmethod
    def _get_rule_port_ranges(rule):
        """ Extracts ports ranges from the NSG rule object
            Returns an array of PortsRange tuples
        """
        properties = rule['properties']
        if 'destinationPortRange' in properties:
            return [PortsRangeHelper._get_port_range(properties['destinationPortRange'])]
        else:
            return [PortsRangeHelper._get_port_range(r)
                    for r in properties['destinationPortRanges']]

    @staticmethod
    def _port_ranges_to_set(ranges):
        """ Converts array of port ranges to the set of integers
            Example: [(10-12), (20,20)] -> {10, 11, 12, 20}
        """
        return set([i for r in ranges for i in range(r.start, r.end + 1)])

    @staticmethod
    def validate_ports_string(ports):
        """ Validate that provided string has proper port numbers:
            1. port number < 65535
            2. range start < range end
        """
        pattern = re.compile('^\\d+(-\\d+)?(,\\d+(-\\d+)?)*$')
        if pattern.match(ports) is None:
            return False

        ranges = PortsRangeHelper._get_string_port_ranges(ports)
        for r in ranges:
            if r.start > r.end or r.start > 65535 or r.end > 65535:
                return False
        return True

    @staticmethod
    def get_ports_set_from_string(ports):
        """ Convert ports range string to the set of integers
            Example: "10-12, 20" -> {10, 11, 12, 20}
        """
        ranges = PortsRangeHelper._get_string_port_ranges(ports)
        return PortsRangeHelper._port_ranges_to_set(ranges)

    @staticmethod
    def get_ports_set_from_rule(rule):
        """ Extract port ranges from NSG rule and convert it to the set of integers
        """
        ranges = PortsRangeHelper._get_rule_port_ranges(rule)
        return PortsRangeHelper._port_ranges_to_set(ranges)

    @staticmethod
    def get_ports_strings_from_list(data):
        """ Transform a list of port numbers to the list of strings with port ranges
            Example: [10, 12, 13, 14, 15] -> ['10', '12-15']
        """
        if len(data) == 0:
            return []

        # Transform diff_ports list to the ranges list
        first = 0
        result = []
        for it in range(1, len(data)):
            if data[first] == data[it] - (it - first):
                continue
            result.append(PortsRangeHelper.PortsRange(start=data[first], end=data[it - 1]))
            first = it

        # Update tuples with strings, representing ranges
        result.append(PortsRangeHelper.PortsRange(start=data[first], end=data[-1]))
        result = [str(x.start) if x.start == x.end else "%i-%i" % (x.start, x.end) for x in result]
        return result

    @staticmethod
    def build_ports_dict(nsg, direction_key, ip_protocol):
        """ Build entire ports array filled with True (Allow), False (Deny) and None(default - Deny)
            based on the provided Network Security Group object, direction and protocol.
        """
        rules = nsg['properties']['securityRules']
        rules = sorted(rules, key=lambda k: k['properties']['priority'])
        ports = {}

        for rule in rules:
            # Skip rules with different direction
            if not StringUtils.equal(direction_key, rule['properties']['direction']):
                continue

            # Check the protocol: possible values are 'TCP', 'UDP', '*' (both)
            # Skip only if rule and ip_protocol are 'TCP'/'UDP' pair.
            protocol = rule['properties']['protocol']
            if not StringUtils.equal(protocol, "*") and \
               not StringUtils.equal(ip_protocol, "*") and \
               not StringUtils.equal(protocol, ip_protocol):
                continue

            IsAllowed = StringUtils.equal(rule['properties']['access'], 'allow')
            ports_set = PortsRangeHelper.get_ports_set_from_rule(rule)

            for p in ports_set:
                if p not in ports:
                    ports[p] = IsAllowed

        return ports


class AppInsightsHelper(object):
    log = logging.getLogger('custodian.azure.utils.AppInsightsHelper')

    @staticmethod
    def get_instrumentation_key(url):
        data = url.split('//')[1]
        try:
            uuid.UUID(data)
        except ValueError:
            values = data.split('/')
            if len(values) != 2:
                AppInsightsHelper.log.warning("Bad format: '%s'" % url)
            return AppInsightsHelper._get_instrumentation_key(values[0], values[1])
        return data

    @staticmethod
    def _get_instrumentation_key(resource_group_name, resource_name):
        from .session import Session
        s = local_session(Session)
        client = s.client('azure.mgmt.applicationinsights.ApplicationInsightsManagementClient')
        try:
            insights = client.components.get(resource_group_name, resource_name)
            return insights.instrumentation_key
        except Exception:
            AppInsightsHelper.log.warning("Failed to retrieve App Insights instrumentation key."
                                          "Resource Group name: %s, App Insights name: %s" %
                                          (resource_group_name, resource_name))
            return ''
