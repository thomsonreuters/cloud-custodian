.. _azure_authentication:

Authentication
==============

The plugin supports four distinct authentication types, including Azure CLI integration, service principal,
MSI, and raw tokens.


Azure CLI
---------

If none of the below environment variables are set, Custodian will attempt to pull credentials and the default
subscription from Azure CLI.  This requires that you have run :code:`az login` and selected your subscription in
Azure CLI first.

Service Principal
-----------------

Service principal must be provided via environment variables.

.. code-block:: bash

    AZURE_TENANT_ID
    AZURE_SUBSCRIPTION_ID
    AZURE_CLIENT_ID
    AZURE_CLIENT_SECRET

You can create a service principal with Azure CLI or via the Azure Portal.
Created Service Principal requires Contributor role to be assigned. 

Azure Portal
~~~~~~~~~~~~

You can follow instructions to create and assigned required permissions to the new Service Principal: 
`How to create Service Principal <https://docs.microsoft.com/en-us/azure/active-directory/develop/howto-create-service-principal-portal>`_

Azure CLI
~~~~~~~~~

.. code-block:: bash

    # select correct subscription
    az account set -s "my subscription name"

    # create service principal
    az ad sp create-for-rbac --name <name> --password <password>

This will yield something like:

.. code-block:: javascript

    {
      "appId": appid,
      "displayName": name,
      "name": name,
      "password": password,
      "tenant": guid
    }

You will need to map it to environment variables for Custodian like this:

.. code-block:: bash

    AZURE_TENANT_ID=tenant
    AZURE_SUBSCRIPTION_ID=subscriptionId
    AZURE_CLIENT_ID=appId
    AZURE_CLIENT_SECRET=password

Created Service Principal already has Contributor role.

c7n-org
~~~~~~~

If you're using a Service Principal across subscriptions with `c7n-org` you'll
need to grant it access to each of the subscriptions.

Please follow this instruction to grant an access: 
`instruction <https://docs.microsoft.com/en-us/azure/active-directory/develop/howto-create-service-principal-portal#assign-the-application-to-a-role>`_

Access Token
------------

Passing access tokens directly is useful for integration or fake test authentication.

For fake test authentication environment variables should be configured as shown below:

.. code-block:: bash

    AZURE_ACCESS_TOKEN=fake_token
    AZURE_SUBSCRIPTION_ID=ea42f556-5106-4743-99b0-c129bfa71a47

You will also find this configuration in tox.ini.

Managed Service Identity
------------------------

Learn about MSI in the
`Azure Documentation <https://docs.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview>`_.

If `AZURE_USE_MSI` is set to any value, Custodian will attempt to use MSI.

If `AZURE_CLIENT_ID` is not set, Custodian will use the System Identity.

If `AZURE_CLIENT_ID` is set, Custodian will use the User Identity which matches the client id.

You must set `AZURE_SUBSCRIPTION_ID` as with the other authentication types.

.. code-block:: bash

    AZURE_USE_MSI=1
    AZURE_SUBSCRIPTION_ID=subscriptionId
    AZURE_CLIENT_ID=clientId

Azure Storage access
====================

If your service principal will be writing logs to storage or leveraging queues
for mailer you should assign Storage roles, either at the subscription
level or resource group/storage account level.

Please note, that you cannot leverage Azure Storage functionality if you use Access Token for authentication.

- `Blob Data Contributor`
- `Queue Data Contributor`

More details about Azure Storage access rights:
`Azure Documents <https://docs.microsoft.com/en-us/azure/storage/common/storage-auth-aad-rbac>`_
