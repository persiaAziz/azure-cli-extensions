# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# # --------------------------------------------------------------------------------------------
from uuid import uuid4

from azure.cli.core.commands.client_factory import get_mgmt_service_client
from azure.cli.core.profiles import ResourceType
from azure.mgmt.resource.resources.models import ResourceGroup
from knack.log import get_logger

from ._database_utils import Database
from ._website_utils import Website
from ._cogsvcs_utils import (
    create_cogsvcs_key,
    get_cogsvcs_key
)

logger = get_logger(__name__)


def create_hack(cmd, name, runtime, location, database=None, ai=None):
    # TODO: Update this to use a default location, or prompt??
    name = name + str(uuid4())[:5]
    # # Create RG
    logger.warning("Creating resource group...")
    _create_resource_group(cmd, name, location)

    if ai:
        logger.warning('Starting creation of Cognitive Services keys...')
        create_cogsvcs_key(cmd, name, location)

    if database:
        logger.warning("Starting database creation job...")
        database = Database(cmd, database, name, location)
        database_poller = database.create()

    logger.warning("Starting website creation job...")
    website = Website(cmd, name, location, runtime)
    website.create()

    if database:
        # Wait for database to complete creation
        while True:
            database_poller.result(15)
            if database_poller.done():
                break

    app_settings = {}

    if database:
        database.admin = database.admin if database.database_type != 'mysql' else database.admin + '@' + database.name
        app_settings.update({
            'DATABASE_HOST': database.host,
            'DATABASE_NAME': database.name,
            'DATABASE_PORT': database.port,
            'DATABASE_USER': database.admin,
            'DATABASE_PASSWORD': database.password,
        })

    if ai:
        app_settings.update({
            'COGSVCS_KEY': get_cogsvcs_key(cmd, name),
            'COGSVCS_CLIENTURL': 'https://{}.api.cognitive.microsoft.com/'.format(location)
        })

    website.update_settings(app_settings)
    website.finalize_resource_group()

    output = {}

    deployment_info = {
        'Deployment url': website.deployment_url,
        'Git login': website.deployment_user_name,
    }

    if website.deployment_user_password:
        deployment_info.update(
            {'Git password': website.deployment_user_password})
    else:
        password_info = 'Cannot retrieve password. To change, use `az webapp deployment user set --user-name {}`'
        deployment_info.update(
            {'Git password info': password_info.format(website.deployment_user_name)})

    deployment_steps = {
        '1- Create git repository': 'git init',
        '2- Add all code': 'git add .',
        '3- Commit code': 'git commit -m \'Initial commit\'',
        '4- Add remote to git': 'git remote add azure ' + website.deployment_url,
        '5- Deploy to Azure': 'git push azure'
    }

    output.update({'Settings and keys': {
        'Note': 'All values are stored as environmental variables on website',
        'Values': app_settings
    }})
    output.update({'Deployment info': deployment_info})
    output.update({'Deployment steps': deployment_steps})
    output.update({'Website url': website.host_name})

    return output


def show_hack(cmd, name):
    return Website(cmd, name, None, None).show()


def _create_resource_group(cmd, name, location):
    client = get_mgmt_service_client(
        cmd.cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES)
    params = ResourceGroup(location=location)
    client.resource_groups.create_or_update(name, params)
