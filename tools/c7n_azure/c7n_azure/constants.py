"""
Azure Functions
"""
# Docker version from https://hub.docker.com/r/microsoft/azure-functions/
FUNCTION_DOCKER_VERSION = 'DOCKER|mcr.microsoft.com/azure-functions/python:latest'
FUNCTION_EXT_VERSION = '~2'
FUNCTION_EVENT_TRIGGER_MODE = 'azure-event-grid'
FUNCTION_TIME_TRIGGER_MODE = 'azure-periodic'
FUNCTION_KEY_URL = 'hostruntime/admin/host/systemkeys/_master?api-version=2018-02-01'
FUNCTION_CONSUMPTION_BLOB_CONTAINER = 'cloud-custodian-packages'
FUNCTION_PACKAGE_SAS_EXPIRY_DAYS = 365 * 10  # 10 years

"""
Event Grid Mode
"""
EVENT_GRID_UPN_CLAIM_JMES_PATH = \
    'data.claims."http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn"'
EVENT_GRID_SP_NAME_JMES_PATH = 'data.claims.appid'
EVENT_GRID_SERVICE_ADMIN_JMES_PATH = \
    'data.claims."http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"'
EVENT_GRID_PRINCIPAL_TYPE_JMES_PATH = 'data.authorization.evidence.principalType'
EVENT_GRID_PRINCIPAL_ROLE_JMES_PATH = 'data.authorization.evidence.role'

"""
Environment Variables
"""
ENV_TENANT_ID = 'AZURE_TENANT_ID'
ENV_CLIENT_ID = 'AZURE_CLIENT_ID'
ENV_SUB_ID = 'AZURE_SUBSCRIPTION_ID'
ENV_CLIENT_SECRET = 'AZURE_CLIENT_SECRET'

ENV_ACCESS_TOKEN = 'AZURE_ACCESS_TOKEN'

ENV_USE_MSI = 'AZURE_USE_MSI'

ENV_FUNCTION_TENANT_ID = 'AZURE_FUNCTION_TENANT_ID'
ENV_FUNCTION_CLIENT_ID = 'AZURE_FUNCTION_CLIENT_ID'
ENV_FUNCTION_SUB_ID = 'AZURE_FUNCTION_SUBSCRIPTION_ID'
ENV_FUNCTION_CLIENT_SECRET = 'AZURE_FUNCTION_CLIENT_SECRET'

# Allow disabling SSL cert validation (ex: custom domain for ASE functions)
ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION = 'CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION'

"""
Authentication Resource
"""
RESOURCE_ACTIVE_DIRECTORY = 'https://management.core.windows.net/'
RESOURCE_STORAGE = 'https://storage.azure.com/'

"""
Threading Variable
"""
DEFAULT_MAX_THREAD_WORKERS = 3
DEFAULT_CHUNK_SIZE = 20

"""
Custom Retry Code Variables
"""
DEFAULT_MAX_RETRY_AFTER = 30
