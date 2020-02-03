#!/usr/bin/env python


import os
import sys
import fnmatch
import yaml
import json
import string
import random
from datetime import datetime, tzinfo, timedelta
import boto3
import botocore
import account_metadata
import assume_role


CFN_PATTERNS = ['.cf.json', '.cf.yml', '.cf.yaml']
TARGET_ACCOUNTS = os.environ['TARGET_ACCOUNTS'].split(',') \
    if 'TARGET_ACCOUNTS' in os.environ else []
TEMPLATE_DIR = sys.argv[1] if len(sys.argv) > 1 else '.'

class UTC(tzinfo):
    """
    UTC object for datetime calculations
    """

    def utcoffset(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return 'UTC'

    def dst(self, dt):
        return timedelta(0)


class DateTimeEncoder(json.JSONEncoder):
    """
    Enable datetime fields conversion to JSON string
    """

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)


def get_account_id_from_arn(arn):
    """
    Get account id from ARN
    """
    return arn.split(':')[4]


def find_files(directory, patterns):
    """
    Recursive find matching files in directory
    """
    for root, _, files in os.walk(directory):
        for basename in files:
            for pattern in patterns:
                if fnmatch.fnmatch(basename, '*{p}'.format(p=pattern)):
                    filename = os.path.join(root, basename)
                    yield filename


def find_templates(template_dir):
    """
    Search for cloudformation templates
    """
    template_files = sorted(
        find_files(directory=template_dir, patterns=CFN_PATTERNS)
    )
    templates = []

    for template_file in template_files:
        template_path = template_file
        dir_name = os.path.dirname(template_file)
        base_name = os.path.basename(template_file)

        for cloudformation_pattern in CFN_PATTERNS:
            if base_name.endswith(cloudformation_pattern):
                template_base = base_name[:-len(cloudformation_pattern)]

        config_files = [
            os.path.join(dir_name, config_file)
            for config_file in os.listdir(dir_name)
                if fnmatch.fnmatch(config_file, '{n}.*.yaml'.format(n=template_base))
                and config_file != base_name
        ]

        if len(config_files) < 1:
            message = 'No config files found for template "{t}"'.format(
                t=template_file)
            raise Exception(message)

        templates.append({
            'template_path': template_path,
            'config_files': config_files
        })
    return templates


def read_config_files(config_files):
    """
    Read per-stack config files
    """

    # Required fields
    required_fields = ['CloudFormationOptions']
    required_cfn_options = ['StackName']

    # Read all config files
    all_config = []
    for config_file in config_files:
        try:
            config_data = open(config_file).read()
            config = yaml.load(config_data, Loader=yaml.FullLoader)
        except ValueError as config_excepton:
            print('Invalid YAML in {f}'.format(f=config_file))
            raise config_excepton

        if isinstance(config, list):
            for config_item in config:
                all_config.append(config_item)
        else:
            all_config.append(config)

    for config in all_config:
        for required_field in required_fields:
            if required_field not in config:
                raise ValueError('Required field "{f}" not found'.format(
                    f=required_field))

        for required_cfn_option in required_cfn_options:
            if required_cfn_option not in config['CloudFormationOptions']:
                msg = 'Required CloudFormationOption "{o}" not found'.format(
                    o=required_cfn_option)
                raise ValueError(msg)

    return all_config


def read_template(template_path):
    """
    Read template file into string
    """
    return open(template_path).read().strip()


def deploy_template(template_path, config_files):
    """
    Read template and apply to stack (create/update)
    """
    print('Deploying template: {tp}'.format(tp=template_path))

    configs = read_config_files(config_files=config_files)
    template_body = read_template(template_path=template_path)
    return [create_stack(config=config, template_body=template_body, template_path=template_path)
            for config in configs]


def create_stack(config, template_body,template_path):
    """
    Create a new stack
    """
    if 'TargetAccountAliases' in config and config['TargetAccountAliases'] != None:
        DeployBucket = None
        if 'DeployBucket' in config:
            DeployBucket = config['DeployBucket']
        return [
            provision_template(
                config=config,
                template_body=template_body,
                account_alias=alias,
                assume_role_arn=account_metadata.get_deploy_role_arn_by_alias(alias),
                cfn_deploybucket=DeployBucket,
                template_path=template_path
            )
            for alias in TARGET_ACCOUNTS
            if alias in config['TargetAccountAliases']
        ]


# def assume_role(role_arn):
#     """
#     Assume role and return dict with temporary credentials
#     """

#     # Do we need to refresh the tokens?
#     cached = role_arn in CACHED_CREDENTIALS

#     # Expired?
#     if cached:
#         # Get expiration from sts token
#         expiration = CACHED_CREDENTIALS[role_arn]['expiration']

#         # Get current time
#         now = datetime.now(UTC())
#         expire_in_seconds = (expiration - now).total_seconds()

#         # Force refresh if token is valid for 10 minutes
#         expired = expire_in_seconds < 600.0

#     # Get STS token if not cached or expired
#     if not cached or expired:
#         sts_client = boto3.client('sts')
#         assume_role_object = sts_client.assume_role(
#             RoleArn=role_arn,
#             RoleSessionName=os.path.basename(sys.argv[0])
#         )
#         credentials = assume_role_object['Credentials']

#         sts_credentials = {
#             'aws_access_key_id': credentials['AccessKeyId'],
#             'aws_secret_access_key': credentials['SecretAccessKey'],
#             'aws_session_token': credentials['SessionToken'],
#             'expiration': credentials['Expiration'],
#         }

#         # Store credentials in cache
#         CACHED_CREDENTIALS[role_arn] = sts_credentials

#     return CACHED_CREDENTIALS[role_arn].copy()


def provision_template(config, template_body, account_alias, assume_role_arn=None,cfn_deploybucket=None,template_path=None):
    """
    Prepare for deployment
    """
    cfn_client_kwargs = {}
    print('Account: {alias}'.format(alias=account_alias))

    if assume_role_arn:
        assume_role_credentials = assume_role.assume_role(role_arn=assume_role_arn)
        del assume_role_credentials['expiration']
        cfn_client_kwargs.update(assume_role_credentials)
    else:
        assume_role_arn = None

    # Create cloudformation client
    cfn_client = assume_role.create_client('cloudformation', **cfn_client_kwargs)

    # Set change set options
    change_set_name = ''.join(random.choice(string.ascii_lowercase)
                              for _ in range(16))

    config['CloudFormationOptions']['ChangeSetName'] = change_set_name
    
    if cfn_deploybucket != None:
        print ("Upload to S3 Bucket {}".format(cfn_deploybucket))
        # Create an S3 client
        s3 = assume_role.create_client('s3', **cfn_client_kwargs)
        filename = os.path.basename(template_path)
        s3.upload_file(template_path, cfn_deploybucket, filename)
        TemplateUrl = 'https://'+cfn_deploybucket+'.s3.amazonaws.com/'+filename

    if cfn_deploybucket:
        config['CloudFormationOptions'].update({'TemplateURL': TemplateUrl})
    elif template_body:
        config['CloudFormationOptions'].update({'TemplateBody': template_body})
    stack_name = config['CloudFormationOptions']['StackName']

    if not stack_exists(client=cfn_client, stack_name=stack_name):
        change_set_type = 'CREATE'
    else:
        change_set_type = 'UPDATE'

    config['CloudFormationOptions']['ChangeSetType'] = change_set_type

    # Tell what we are doing
    msg = '  - {change_set_type} stack: {stack_name}'.format(
        change_set_type=change_set_type.lower().title(),
        stack_name=stack_name)

    if assume_role_arn:
        msg = '{msg} (with assume role: {assumed_role})'.format(
            msg=msg,
            assumed_role=assume_role_arn
        )
    print(msg)

    create_change_set(client=cfn_client, config=config)
    execute = execute_change_set(client=cfn_client, config=config)

    print("  - Done!\n")
    if execute is not None and 'ResponseFile' in config:
        response_fd = open(config['ResponseFile'], 'a')
        response_fd.write(
            json.dumps(
                execute,
                indent=4,
                sort_keys=True,
                cls=DateTimeEncoder)
        )
        response_fd.close()

    return execute


def create_change_set(client, config):
    """
    Create CloudFormation changeset
    """
    change_set_name = config['CloudFormationOptions']['ChangeSetName']
    stack_name = config['CloudFormationOptions']['StackName']
    change_set_kwargs = {
        'ChangeSetName': change_set_name,
        'StackName': stack_name
    }

    response = client.create_change_set(**config['CloudFormationOptions'])

    waiter = client.get_waiter('change_set_create_complete')
    try:
        waiter.wait(**change_set_kwargs)
    except botocore.exceptions.WaiterError:
        pass

    return response


def execute_change_set(client, config):
    """
    Execute previous generated changeset
    """
    change_set_name = config['CloudFormationOptions']['ChangeSetName']
    stack_name = config['CloudFormationOptions']['StackName']
    change_set_kwargs = {
        'ChangeSetName': change_set_name,
        'StackName': stack_name
    }

    no_changes = 'The submitted information didn\'t contain changes'

    change_set_status = client.describe_change_set(**change_set_kwargs)
    status = change_set_status['Status']
    status_reason = change_set_status['StatusReason'] \
        if 'StatusReason' in change_set_status else None

    # Detect errors
    if status == 'FAILED' and status_reason.startswith(no_changes):
        client.delete_change_set(**change_set_kwargs)
        print("  - Info: {msg}".format(msg=no_changes))
        return None
    elif status == 'FAILED':
        print('  - Error: {reason}'.format(reason=status_reason))
        return change_set_status

    # Execute change set
    client.execute_change_set(**change_set_kwargs)

    waiter_type = 'stack_create_complete' \
        if config['CloudFormationOptions']['ChangeSetType'] == 'CREATE' \
        else 'stack_update_complete'
    waiter = client.get_waiter(waiter_type)

    print('  - Change set "{change_set}" is being executed, waiting...'.format(
        change_set=change_set_name))
    waiter.wait(StackName=stack_name)

    return client.describe_stacks(StackName=stack_name)


def create_client(namespace, **session_kwargs):
    """
    Return boto3 client object
    """
    session = boto3.Session(**session_kwargs)
    return session.client(namespace)


def stack_exists(client, stack_name):
    """
    Check if check with name already exists
    """
    try:
        client.describe_stacks(StackName=stack_name)
    except botocore.exceptions.ClientError:
        return False
    return True

def find_duplicate_templates(template_path, config_files):
    """
    Check for target stacks with the same name
    """
    configs = read_config_files(config_files=config_files)

    stacks_by_accounts = {}
    for config in configs:
        if 'TargetAccountAliases' in config and config['TargetAccountAliases'] != None:
            for account in config['TargetAccountAliases']:
                if account not in stacks_by_accounts:
                    stacks_by_accounts[account] = []

                stack_name = config['CloudFormationOptions']['StackName']
                stacks_by_accounts[account].append(stack_name)

    errors = []

    for account, stacks in list(stacks_by_accounts.items()):
        duplicates = [x for n, x in enumerate(stacks) if x in stacks[:n]]

        if duplicates:
            errors.append('Account "{}": {}'.format(account, duplicates))

    if errors:
        error_msg = 'Duplicate templates found'
        error_stacks = '\n'.join(errors)
        exception_msg = '{}:\n{}'.format(error_msg, error_stacks)
        raise ValueError(exception_msg)

def main():
    """
    Run this code
    """
    for templates in find_templates(template_dir=TEMPLATE_DIR):
        # First check if there are no duplicates
        find_duplicate_templates(**templates)
        # Deploy
        deploy_template(**templates)


if __name__ == '__main__':
    main()
