# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, ConfigSource
from c7n.tags import universal_augment


@resources.register('acm-certificate')
class Certificate(QueryResourceManager):

    class resource_type(object):
        service = 'acm'
        enum_spec = ('list_certificates', 'CertificateSummaryList', None)
        id = 'CertificateArn'
        name = 'DomainName'
        date = 'CreatedAt'
        dimension = None
        detail_spec = (
            "describe_certificate", "CertificateArn",
            'CertificateArn', 'Certificate')
        config_type = "AWS::ACM::Certificate"
        filter_name = None
        type = 'certificate'
        universal_taggable = object()

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeCertificate(self)
        elif source_type == 'config':
            return ConfigSource(self)
        raise ValueError("Unsupported source: %s for %s" % (
            source_type, self.resource_type.config_type))


class DescribeCertificate(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)
