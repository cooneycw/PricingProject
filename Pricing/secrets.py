import boto3
import base64
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Use this code snippet in your app.
# If you need more information about configurations or implementing the sample code, visit the AWS docs:
# https://aws.amazon.com/developers/getting-started/python/

# add aws_access_key_id / aws_secret_access_key to environment variables
global AWS_ACCESS
global AWS_SECRET
global DEV

load_dotenv(verbose=True)
AWS_ACCESS = os.environ.get('aws_access_key_id')
AWS_SECRET = os.environ.get('aws_secret_access_key')
DEV = os.environ.get('dev')

# print(f'AWS_ACCESS: {AWS_ACCESS}  AWS_SECRET: {AWS_SECRET}  DEV: {DEV}')


def get_secrets():
    secret_name = "arn:aws:secretsmanager:us-east-1:547847502175:secret:the6ixclandjango-QubtHJ"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        aws_access_key_id=AWS_ACCESS,
        aws_secret_access_key=AWS_SECRET,
        service_name='secretsmanager',
        region_name=region_name
    )
    cwc = 0
    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS key.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])

    # Your code goes here.
    return secret