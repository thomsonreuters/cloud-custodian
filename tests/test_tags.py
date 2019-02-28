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
"""Most tags tests within their corresponding resource tags, we use this
module to test some universal tagging infrastructure not directly exposed.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import time
from mock import MagicMock, call

from c7n.tags import universal_retry, coalesce_copy_user_tags
from c7n.exceptions import PolicyExecutionError, PolicyValidationError

from .common import BaseTest


class UniversalTagRetry(BaseTest):

    def test_retry_no_error(self):
        mock = MagicMock()
        mock.side_effect = [{"Result": 42}]
        self.assertEqual(universal_retry(mock, []), {"Result": 42})
        mock.assert_called_once()

    def test_retry_failure_reduced_set(self):
        sleep = MagicMock()
        self.patch(time, "sleep", sleep)
        method = MagicMock()
        method.side_effect = [
            {"FailedResourcesMap": {"arn:abc": {"ErrorCode": "ThrottlingException"}}},
            {"Result": 32},
        ]
        self.assertEqual(
            universal_retry(method, ["arn:abc", "arn:def"]), {"Result": 32}
        )
        sleep.assert_called_once()
        self.assertTrue(
            method.call_args_list == [
                call(ResourceARNList=["arn:abc", "arn:def"]),
                call(ResourceARNList=["arn:abc"]),
            ]
        )

    def test_retry_pass_error(self):
        method = MagicMock()
        method.side_effect = [
            {"FailedResourcesMap": {"arn:abc": {"ErrorCode": "PermissionDenied"}}}
        ]
        self.assertRaises(Exception, universal_retry, method, ["arn:abc"])


class CoalesceCopyUserTags(BaseTest):
    def test_copy_bool_user_tags(self):
        tags = [{'Key': 'test-key', 'Value': 'test-value'}]
        resource = {
            'Tags': tags
        }

        copy_tags = True
        user_tags = []

        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, tags)

        copy_tags = False
        user_tags = {'test-key-1': 'test-value'}

        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [{'Key': 'test-key-1', 'Value': 'test-value'}])

    def test_copy_list_user_tags(self):
        tags = [
            {
                'Key': 'test-key-1',
                'Value': 'test-value'
            },
            {
                'Key': 'test-key',
                'Value': 'test-value'
            }
        ]
        resource = {
            'Tags': tags
        }

        copy_tags = ['test-key-1']
        user_tags = []

        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [{'Key': 'test-key-1', 'Value': 'test-value'}])

    def test_copy_asterisk_user_tags(self):
        tags = [
            {
                'Key': 'test-key-1',
                'Value': 'test-value'
            },
            {
                'Key': 'test-key',
                'Value': 'test-value'
            }
        ]

        resource = {
            'Tags': tags
        }

        copy_tags = ['*']
        user_tags = []
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, tags)

    def test_empty_resource_tags(self):
        resource = {}
        copy_tags = ['test-key-1']
        user_tags = {'user-key': 'test-value'}
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [{'Key': 'user-key', 'Value': 'test-value'}])

    def test_copy_user_tags_conflict(self):
        tags = [
            {
                'Key': 'test-key-1',
                'Value': 'test-value'
            },
            {
                'Key': 'test-key',
                'Value': 'test-value'
            }
        ]

        resource = {
            'Tags': tags
        }

        copy_tags = ['*']
        user_tags = [{'Key': 'test-key', 'Value': 'test-value-user'}]
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(len(final_tags), 2)
        self.assertTrue({'Key': 'test-key-1', 'Value': 'test-value'} in final_tags)
        self.assertTrue({'Key': 'test-key', 'Value': 'test-value-user'} in final_tags)

    def test_empty_response(self):
        resource = {}
        user_tags = {}
        copy_tags = []
        final_tags = coalesce_copy_user_tags(resource, copy_tags, user_tags)
        self.assertEqual(final_tags, [])


class CopyRelatedResourceTag(BaseTest):
    def test_copy_related_resource_tag_all(self):
        session_factory = self.replay_flight_data("test_tags_copy_related_resource_tags_all")
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "Tags": "empty"
                    }
                ],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "tags": "*"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ec2', 'us-east-1')

        snap = client.describe_snapshots(SnapshotIds=[resources[0]['SnapshotId']])['Snapshots']
        vol = client.describe_volumes(VolumeIds=[resources[0]['VolumeId']])['Volumes']

        self.assertEqual(snap[0]['Tags'], vol[0]['Tags'])

    def test_copy_related_resource_tag_partial(self):
        session_factory = self.replay_flight_data("test_tags_copy_related_resource_tag_partial")
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "filters": [
                    {
                        "Tags": "empty"
                    }
                ],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "tags": [
                            "tag1",
                            "tag3"
                        ]
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ec2', 'us-east-1')

        snap = client.describe_snapshots(SnapshotIds=[resources[0]['SnapshotId']])['Snapshots']
        vol = client.describe_volumes(VolumeIds=[resources[0]['VolumeId']])['Volumes']

        vol_tags = {t['Key']: t['Value'] for t in vol[0]['Tags']}
        snap_tags = {t['Key']: t['Value'] for t in snap[0]['Tags']}

        self.assertFalse(vol_tags == snap_tags)

        self.assertEqual(snap_tags['tag1'], vol_tags['tag1'])
        self.assertEqual(snap_tags['tag3'], vol_tags['tag3'])

        self.assertTrue(vol_tags['tag2'])
        self.assertFalse(snap_tags.get('tag2'))

    def test_copy_related_resource_tag_missing(self):
        session_factory = self.replay_flight_data("test_tags_copy_related_resource_tag_missing")
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "skip_missing": False,
                        "tags": [
                            "*"
                        ]
                    }
                ]
            },
            session_factory=session_factory
        )

        with self.assertRaises(PolicyExecutionError):
            p.run()

    def test_copy_related_resource_tag_validate(self):
        p = self.load_policy(
            {
                "name": "copy-related-resource-tags-snapshots-volumes",
                "resource": "ebs-snapshot",
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "resource": "ebs",
                        "key": "VolumeId",
                        "skip_missing": False,
                        "tags": [
                            "*"
                        ]
                    }
                ]
            }
        )
        self.assertFalse(p.validate())

        policy = {
            "name": "copy-related-resource-tags-snapshots-volumes",
            "resource": "ebs-snapshot",
            "actions": [
                {
                    "type": "copy-related-tag",
                    "resource": "not-a-resource",
                    "key": "VolumeId",
                    "skip_missing": False,
                    "tags": [
                        "*"
                    ]
                }
            ]
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy)
