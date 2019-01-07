# Copyright 2017 Capital One Services, LLC
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
import smtplib
from email.mime.text import MIMEText
from itertools import chain
import six

from .ldap_lookup import LdapLookup
from c7n_mailer.utils_email import is_email
from .utils import (
    format_struct, get_message_subject, get_resource_tag_targets,
    get_rendered_jinja, kms_decrypt)

# Those headers are defined as follows:
#  'X-Priority': 1 (Highest), 2 (High), 3 (Normal), 4 (Low), 5 (Lowest)
#              Non-standard, cf https://people.dsv.su.se/~jpalme/ietf/ietf-mail-attributes.html
#              Set by Thunderbird
#  'X-MSMail-Priority': High, Normal, Low
#              Cf Microsoft https://msdn.microsoft.com/en-us/library/gg671973(v=exchg.80).aspx
#              Note: May increase SPAM level on Spamassassin:
#                    https://wiki.apache.org/spamassassin/Rules/MISSING_MIMEOLE
#  'Priority': "normal" / "non-urgent" / "urgent"
#              Cf https://tools.ietf.org/html/rfc2156#section-5.3.6
#  'Importance': "low" / "normal" / "high"
#              Cf https://tools.ietf.org/html/rfc2156#section-5.3.4
PRIORITIES = {
    '1': {
        'X-Priority': '1 (Highest)',
        'X-MSMail-Priority': 'High',
        'Priority': 'urgent',
        'Importance': 'high',
    },
    '2': {
        'X-Priority': '2 (High)',
        'X-MSMail-Priority': 'High',
        'Priority': 'urgent',
        'Importance': 'high',
    },
    '3': {
        'X-Priority': '3 (Normal)',
        'X-MSMail-Priority': 'Normal',
        'Priority': 'normal',
        'Importance': 'normal',
    },
    '4': {
        'X-Priority': '4 (Low)',
        'X-MSMail-Priority': 'Low',
        'Priority': 'non-urgent',
        'Importance': 'low',
    },
    '5': {
        'X-Priority': '5 (Lowest)',
        'X-MSMail-Priority': 'Low',
        'Priority': 'non-urgent',
        'Importance': 'low',
    }
}


class EmailDelivery(object):

    def __init__(self, config, session, logger):
        self.config = config
        self.logger = logger
        self.session = session
        self.aws_ses = session.client('ses', region_name=config.get('ses_region'))
        self.ldap_lookup = self.get_ldap_connection()

    def get_ldap_connection(self):
        if self.config.get('ldap_uri'):
            self.config['ldap_bind_password'] = kms_decrypt(self.config, self.logger,
                                                            self.session, 'ldap_bind_password')
            return LdapLookup(self.config, self.logger)
        return None

    def priority_header_is_valid(self, priority_header):
        try:
            priority_header_int = int(priority_header)
        except ValueError:
            return False
        if priority_header_int and 0 < int(priority_header_int) < 6:
            return True
        else:
            self.logger.warning('mailer priority_header is not a valid string from 1 to 5')
            return False

    def get_valid_emails_from_list(self, targets):
        emails = []
        for target in targets:
            if is_email(target):
                emails.append(target)
        return emails

    def get_event_owner_email(self, targets, event):
        if 'event-owner' in targets:
            aws_username = self.get_aws_username_from_event(event)
            if aws_username:
                # is using SSO, the target might already be an email
                if is_email(aws_username):
                    return [aws_username]
                # if the LDAP config is set, lookup in ldap
                elif self.config.get('ldap_uri', False):
                    return self.ldap_lookup.get_email_to_addrs_from_uid(aws_username)
                # the org_domain setting is configured, append the org_domain
                # to the username from AWS
                elif self.config.get('org_domain', False):
                    org_domain = self.config.get('org_domain', False)
                    self.logger.info('adding email %s to targets.', aws_username + '@' + org_domain)
                    return [aws_username + '@' + org_domain]
                else:
                    self.logger.warning('unable to lookup owner email. \
                            Please configure LDAP or org_domain')
            else:
                self.logger.info('no aws username in event')
        return []

    def get_ldap_emails_from_resource(self, sqs_message, resource):
        ldap_uid_tag_keys = self.config.get('ldap_uid_tags', [])
        ldap_uri = self.config.get('ldap_uri', False)
        if not ldap_uid_tag_keys or not ldap_uri:
            return []
        # this whole section grabs any ldap uids (including manager emails if option is on)
        # and gets the emails for them and returns an array with all the emails
        ldap_uid_tag_values = get_resource_tag_targets(resource, ldap_uid_tag_keys)
        email_manager = sqs_message['action'].get('email_ldap_username_manager', False)
        ldap_uid_emails = []
        # some types of resources, like iam-user have 'Username' in the resource, if the policy
        # opted in to resource_ldap_lookup_username: true, we'll do a lookup and send an email
        if sqs_message['action'].get('resource_ldap_lookup_username'):
            ldap_uid_emails = ldap_uid_emails + self.ldap_lookup.get_email_to_addrs_from_uid(
                resource.get('UserName'),
                manager=email_manager
            )
        for ldap_uid_tag_value in ldap_uid_tag_values:
            ldap_emails_set = self.ldap_lookup.get_email_to_addrs_from_uid(
                ldap_uid_tag_value,
                manager=email_manager
            )
            ldap_uid_emails = ldap_uid_emails + ldap_emails_set
        return ldap_uid_emails

    def get_resource_owner_emails_from_resource(self, sqs_message, resource):
        if 'resource-owner' not in sqs_message['action']['to']:
            return []
        resource_owner_tag_keys = self.config.get('contact_tags', [])
        resource_owner_tag_values = get_resource_tag_targets(resource, resource_owner_tag_keys)
        explicit_emails = self.get_valid_emails_from_list(resource_owner_tag_values)

        # resolve the contact info from ldap
        non_email_ids = list(set(resource_owner_tag_values).difference(explicit_emails))
        ldap_emails = list(chain.from_iterable([self.ldap_lookup.get_email_to_addrs_from_uid
                                              (uid) for uid in non_email_ids]))

        return list(chain(explicit_emails, ldap_emails))

    def get_account_emails(self, sqs_message):
        email_list = []

        if 'account-emails' not in sqs_message['action']['to']:
            return []

        account_id = sqs_message.get('account_id', None)
        self.logger.debug('get_account_emails for account_id: %s.', account_id)

        if account_id is not None:
            account_email_mapping = self.config.get('account_emails', {})
            self.logger.debug(
                'get_account_emails account_email_mapping: %s.', account_email_mapping)
            email_list = account_email_mapping.get(account_id, [])
            self.logger.debug('get_account_emails email_list: %s.', email_list)

        return self.get_valid_emails_from_list(email_list)

    # this function returns a dictionary with a tuple of emails as the key
    # and the list of resources as the value. This helps ensure minimal emails
    # are sent, while only ever sending emails to the respective parties.
    def get_email_to_addrs_to_resources_map(self, sqs_message):
        # policy_to_emails always get sent to any email msg that goes out
        # these were manually set by the policy writer in notify to section
        # or it's an email from an aws event username from an ldap_lookup
        email_to_addrs_to_resources_map = {}
        targets = sqs_message['action']['to'] + \
            (sqs_message['action']['cc'] if 'cc' in sqs_message['action'] else [])
        no_owner_targets = self.get_valid_emails_from_list(
            sqs_message['action'].get('owner_absent_contact', [])
        )
        # policy_to_emails includes event-owner if that's set in the policy notify to section
        policy_to_emails = self.get_valid_emails_from_list(targets)
        # if event-owner is set, and the aws_username has an ldap_lookup email
        # we add that email to the policy emails for these resource(s) on this sqs_message
        event_owner_email = self.get_event_owner_email(targets, sqs_message['event'])

        account_emails = self.get_account_emails(sqs_message)

        policy_to_emails = policy_to_emails + event_owner_email + account_emails
        for resource in sqs_message['resources']:
            # this is the list of emails that will be sent for this resource
            resource_emails = []
            # add in any ldap emails to resource_emails
            resource_emails = resource_emails + self.get_ldap_emails_from_resource(
                sqs_message,
                resource
            )
            resource_emails = resource_emails + policy_to_emails
            # add in any emails from resource-owners to resource_owners
            ro_emails = self.get_resource_owner_emails_from_resource(
                sqs_message,
                resource
            )

            resource_emails = resource_emails + ro_emails
            # if 'owner_absent_contact' was specified in the policy and no resource
            # owner emails were found, add those addresses
            if len(ro_emails) < 1 and len(no_owner_targets) > 0:
                resource_emails = resource_emails + no_owner_targets
            # we allow multiple emails from various places, we'll unique with set to not have any
            # duplicates, and we'll also sort it so we always have the same key for other resources
            # and finally we'll make it a tuple, since that is hashable and can be a key in a dict
            resource_emails = tuple(sorted(set(resource_emails)))
            # only if there are valid emails available, add it to the map
            if resource_emails:
                email_to_addrs_to_resources_map.setdefault(resource_emails, []).append(resource)
        if email_to_addrs_to_resources_map == {}:
            self.logger.debug('Found no email addresses, sending no emails.')
        # eg: { ('milton@initech.com', 'peter@initech.com'): [resource1, resource2, etc] }
        return email_to_addrs_to_resources_map

    def get_to_addrs_email_messages_map(self, sqs_message):
        to_addrs_to_resources_map = self.get_email_to_addrs_to_resources_map(sqs_message)
        to_addrs_to_mimetext_map = {}
        for to_addrs, resources in six.iteritems(to_addrs_to_resources_map):
            to_addrs_to_mimetext_map[to_addrs] = self.get_mimetext_message(
                sqs_message,
                resources,
                list(to_addrs)
            )
        # eg: { ('milton@initech.com', 'peter@initech.com'): mimetext_message }
        return to_addrs_to_mimetext_map

    def send_smtp_email(self, smtp_server, message, to_addrs):
        smtp_port = int(self.config.get('smtp_port', 25))
        smtp_ssl = bool(self.config.get('smtp_ssl', True))
        smtp_connection = smtplib.SMTP(smtp_server, smtp_port)
        if smtp_ssl:
            smtp_connection.starttls()
            smtp_connection.ehlo()
        if self.config.get('smtp_username') or self.config.get('smtp_password'):
            smtp_username = self.config.get('smtp_username')
            smtp_password = self.config.get('smtp_password')
            smtp_connection.login(smtp_username, smtp_password)
        smtp_connection.sendmail(message['From'], to_addrs, message.as_string())
        smtp_connection.quit()

    def get_mimetext_message(self, sqs_message, resources, to_addrs):
        body = get_rendered_jinja(
            to_addrs, sqs_message, resources, self.logger,
            'template', 'default', self.config['templates_folders'])
        if not body:
            return None
        email_format = sqs_message['action'].get('template_format', None)
        if not email_format:
            email_format = sqs_message['action'].get(
                'template', 'default').endswith('html') and 'html' or 'plain'
        subject = get_message_subject(sqs_message)
        from_addr = sqs_message['action'].get('from', self.config['from_address'])
        message = MIMEText(body, email_format, 'utf-8')
        message['From'] = from_addr
        message['To'] = ', '.join(to_addrs)
        message['Subject'] = subject
        priority_header = sqs_message['action'].get('priority_header', None)
        if priority_header and self.priority_header_is_valid(
            sqs_message['action']['priority_header']
        ):
            priority_headers = PRIORITIES[str(priority_header)].copy()
            for key in priority_headers:
                message[key] = priority_headers[key]
        return message

    def send_c7n_email(self, sqs_message, email_to_addrs, mimetext_msg):
        try:
            # if smtp_server is set in mailer.yml, send through smtp
            smtp_server = self.config.get('smtp_server')
            if smtp_server:
                self.send_smtp_email(smtp_server, mimetext_msg, email_to_addrs)
            # if smtp_server isn't set in mailer.yml, use aws ses normally.
            else:
                self.aws_ses.send_raw_email(RawMessage={'Data': mimetext_msg.as_string()})
        except Exception as error:
            self.logger.warning(
                "Error policy:%s account:%s sending to:%s \n\n error: %s\n\n mailer.yml: %s" % (
                    sqs_message['policy'],
                    sqs_message.get('account', ''),
                    email_to_addrs,
                    error,
                    self.config
                )
            )
        self.logger.info("Sending account:%s policy:%s %s:%s email:%s to %s" % (
            sqs_message.get('account', ''),
            sqs_message['policy']['name'],
            sqs_message['policy']['resource'],
            str(len(sqs_message['resources'])),
            sqs_message['action'].get('template', 'default'),
            email_to_addrs))

    # https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
    def get_aws_username_from_event(self, event):
        if event is None:
            return None
        identity = event.get('detail', {}).get('userIdentity', {})
        if not identity:
            self.logger.warning("Could not get recipient from event \n %s" % (
                format_struct(event)))
            return None
        if identity['type'] == 'AssumedRole':
            self.logger.debug(
                'In some cases there is no ldap uid is associated with AssumedRole: %s',
                identity['arn'])
            self.logger.debug(
                'We will try to assume that identity is in the AssumedRoleSessionName')
            user = identity['arn'].rsplit('/', 1)[-1]
            if user is None or user.startswith('i-') or user.startswith('awslambda'):
                return None
            if ':' in user:
                user = user.split(':', 1)[-1]
            return user
        if identity['type'] == 'IAMUser' or identity['type'] == 'WebIdentityUser':
            return identity['userName']
        if identity['type'] == 'Root':
            return None
        # this conditional is left here as a last resort, it should
        # be better documented with an example UserIdentity json
        if ':' in identity['principalId']:
            user_id = identity['principalId'].split(':', 1)[-1]
        else:
            user_id = identity['principalId']
        return user_id
