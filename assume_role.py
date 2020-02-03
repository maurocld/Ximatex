#!/usr/bin/env python


import os
import sys
import boto3
import json
from datetime import datetime, tzinfo, timedelta

CACHED_CREDENTIALS = {}

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

def get_client(client_namespace, assume_role_arn=None):
    client_kwargs = {}

    if assume_role_arn:
        assume_role_credentials = assume_role(role_arn=assume_role_arn)
        del assume_role_credentials['expiration']
        client_kwargs.update(assume_role_credentials)
    else:
        assume_role_arn = None

    client_kwargs.update(assume_role_credentials)
    return create_client(client_namespace, **client_kwargs)


def create_client(namespace, **session_kwargs):
    session = boto3.Session(**session_kwargs)
    return session.client(namespace)

def assume_role(role_arn):
    """
    Assume role and return dict with temporary credentials
    """

    # Do we need to refresh the tokens?
    cached = role_arn in CACHED_CREDENTIALS

    # Expired?
    if cached:
        # Get expiration from sts token
        expiration = CACHED_CREDENTIALS[role_arn]['expiration']

        # Get current time
        now = datetime.now(UTC())
        expire_in_seconds = (expiration - now).total_seconds()

        # Force refresh if token is valid for 10 minutes
        expired = expire_in_seconds < 600.0

    # Get STS token if not cached or expired
    if not cached or expired:
        sts_client = boto3.client('sts')
        assume_role_object = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=os.path.basename(sys.argv[0])
        )
        credentials = assume_role_object['Credentials']

        sts_credentials = {
            'aws_access_key_id': credentials['AccessKeyId'],
            'aws_secret_access_key': credentials['SecretAccessKey'],
            'aws_session_token': credentials['SessionToken'],
            'expiration': credentials['Expiration'],
        }

        # Store credentials in cache
        CACHED_CREDENTIALS[role_arn] = sts_credentials

    return CACHED_CREDENTIALS[role_arn].copy()
#