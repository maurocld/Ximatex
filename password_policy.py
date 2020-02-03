#!/usr/bin/env python
import os
import sys
import yaml
import boto3
from botocore.exceptions import ClientError
import account_metadata
import assume_role
#
PASSWORD_POLICY_FILENAME = 'data/password_policy.yaml'

def read_password_policy(filename=PASSWORD_POLICY_FILENAME):
    yaml_password_policy = open(filename, 'r')
    password_policy = yaml.load(yaml_password_policy)
    return password_policy['PasswordPolicy']

def get_client(client_namespace, assume_role_arn=None):
    client_kwargs = {}

    if assume_role_arn:
        assume_role_credentials = assume_role.assume_role(role_arn=assume_role_arn)
        del assume_role_credentials['expiration']
        client_kwargs.update(assume_role_credentials)
    else:
        assume_role_arn = None

    client_kwargs.update(assume_role_credentials)
    return create_client(client_namespace, **client_kwargs)

def create_client(namespace, **session_kwargs):
    session = boto3.Session(**session_kwargs)
    return session.client(namespace)

def get_pwd_policy(iam_client):
    try:
      return iam_client.get_account_password_policy()['PasswordPolicy']
    except iam_client.exceptions.NoSuchEntityException:
      return {}

def up_to_date_policy(current_policy, pwd_policy):
    return current_policy == pwd_policy

def update_policy(iam_client):
    iam_client.update_account_password_policy(
        MinimumPasswordLength=pwd_policy['MinimumPasswordLength'],
        RequireSymbols=pwd_policy['RequireSymbols'],
        RequireNumbers=pwd_policy['RequireNumbers'],
        RequireUppercaseCharacters=pwd_policy['RequireUppercaseCharacters'],
        RequireLowercaseCharacters=pwd_policy['RequireLowercaseCharacters'],
        AllowUsersToChangePassword=pwd_policy['AllowUsersToChangePassword'],
        MaxPasswordAge=pwd_policy['MaxPasswordAge'],
        PasswordReusePrevention=pwd_policy['PasswordReusePrevention'],
        HardExpiry=pwd_policy['HardExpiry']
    )

def check_policy():
    for account in [
        account.strip() for account in os.environ['TARGET_ACCOUNTS'].split(',')
    ]:
        role_arn = account_metadata.get_deploy_role_arn_by_alias(account)
        client = get_client('iam', assume_role_arn=role_arn)
        policy = get_pwd_policy(iam_client=client)

        if not up_to_date_policy(policy, pwd_policy):
            print('Updating password policy on account: ', account)
            update_policy(iam_client=client)
        else:
            print('Password policy on account %s is up to date' % account)

if __name__ == '__main__':
    pwd_policy = read_password_policy()
    check_policy()
