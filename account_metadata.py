#!/usr/bin/env python


import yaml

ACCOUNTS_FILENAME = 'data/accounts.yaml'

def read_accounts(filename=ACCOUNTS_FILENAME):
    yaml_accounts = open(filename, 'r')
    accounts = yaml.load(yaml_accounts, Loader=yaml.FullLoader)
    return accounts


def exactly_one_result(items):
    if len(items) == 0 or len(items) > 1:
        raise ValueError
    return items[0]


def get_account_by_id(account_id):
    accounts = read_accounts()['Accounts']
    matches = [
        account for account in accounts
        if account['Id'] == account_id
    ]
    return exactly_one_result(matches)


def get_account_by_alias(account_alias):
    accounts = read_accounts()['Accounts']
    matches = [
        account for account in accounts
        if account['Alias'] == account_alias
    ]
    return exactly_one_result(matches)


def get_deploy_role_arn_by_id(account_id):
    this_account = get_account_by_id(account_id=account_id)
    return construct_role_arn(account_info=this_account)


def get_deploy_role_arn_by_alias(account_alias):
    this_account = get_account_by_alias(account_alias=account_alias)
    return construct_role_arn(account_info=this_account)


def construct_role_arn(account_info):
    role_items = {
        'id': str(account_info['Id']).zfill(12),
        'role': account_info['DeployRole']
    }

    role_arn = 'arn:aws:iam::{id}:role/{role}'.format(**role_items)
    return role_arn

