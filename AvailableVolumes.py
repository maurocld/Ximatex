import boto3
import os
import logging

LOGLEVEL = os.getenv('LOGLEVEL', 'INFO').strip()
CURR_ACCOUNT_ID = boto3.client('sts').get_caller_identity().get('Account')
ACCOUNTS = ['335484626233','364517926495', '770831410194', '908021385260', '842033685690', '918677289364', '883656117518', '002779451522', '289573883497', '504057805512', '631114505105', '060681614320', '618470607968', '120298155027', '677985655788', '900858092965', '419792440550']
TESTACCOUNTS = ['002779451522','782381283173']
DEST_ROLE_NAME = str(os.getenv('DEST_ROLE_NAME', 'AllowDescribeVolumes')).strip()
REGION = os.getenv('AWS_DEFAULT_REGION')

logger = logging.getLogger()
logging.basicConfig()
logger.setLevel(LOGLEVEL.upper())

def role_arn_to_session(**args):
    client = boto3.client('sts')
    response = client.assume_role(**args)
    return boto3.Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken'])
        
def report_connection_lost_ids(lijst, event):
    ses_session = get_session( 'ses', CURR_ACCOUNT_ID )
    response = ses_session.send_email(
        Source='unisystems@gmail.com',
        Destination={
            'ToAddresses': [ 'unisystems@gmail.com', ]
        },
        Message={
            'Subject': {
                'Charset': 'UTF-8',
                'Data': 'Report on all Available EBS Volumes'
            },
            'Body': {
                'Text': {
                    'Charset': 'UTF-8',
                    'Data': str(lijst)
                }
            }
        }
    )

def get_session(service, account):
    """Switch role to other account for some service client."""
    if account == CURR_ACCOUNT_ID:
        service_session = boto3.client(service, region_name=REGION)
    else:  
        session = role_arn_to_session(
            RoleArn='arn:aws:iam::' + account + ':role/' + DEST_ROLE_NAME,
            RoleSessionName='AmiSession' )
        service_session = session.client(service, region_name=REGION)
    return service_session
    
def lambda_handler(event, context):
    
    friendlyaccountnames={
        "364517926495":"rfh-logging",
        "908021385260":"rfh-audit",
        "842033685690":"rfh-iam",
        "918677289364":"rfh-build",
        "883656117518":"rfh-backup",
        "770831410194":"rfh-shared-live",
        "002779451522":"rfh-sandbox",
        "782381283173":"rfh-experimentalbox",
        "289573883497":"rfh-platform-sandbox",
        "504057805512":"rfh-commerce-staging",
        "631114505105":"rfh-finance-staging",
        "060681614320":"rfh-operations-staging",
        "618470607968":"rfh-support-staging",
        "335484626233":"rfh-shared-staging",
        "120298155027":"rfh-commerce-live",
        "677985655788":"rfh-finance-live",
        "900858092965":"rfh-operations-live",
        "419792440550":"rfh-support-live"
    }          
    
    lijst = []    
    for account in TESTACCOUNTS:
        
        if account == CURR_ACCOUNT_ID:
            client = boto3.client('ec2', region_name=REGION)
        else:  
            session = role_arn_to_session(
                RoleArn='arn:aws:iam::' + account + ':role/' + DEST_ROLE_NAME,
                RoleSessionName='ConfigSession' )
            client = session.client('ec2', region_name=REGION)
    
#        client = boto3.client('ssm', region_name=REGION)
        response = client.describe_volumes(Filters=[
            {
                'Name': 'status',
                'Values': [
                    'available',
                ]
            },
        ],
        MaxResults=50
#       NextToken='string'
        )
        for volume in response["Volumes"]:
           lijst.extend((friendlyaccountnames[account], volume['VolumeId']))
    
    print('AvailableVolumes')       
    print(lijst)
    report_connection_lost_ids(lijst, event)    
