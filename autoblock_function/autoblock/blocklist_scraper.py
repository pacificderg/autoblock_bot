import boto3
import os
import zipfile

ROLE_TABLE_NAME = os.environ.get('ROLE_TABLE_NAME', 'Roles')
ROLE_USERS_INDEX = os.environ.get('ROLE_USERS_INDEX', 'role_users')
OUTPUT_BUCKET_NAME = os.environ.get('OUTPUT_BUCKET_NAME', 'output_bucket')
BLACKLIST_KEY = 'autoblock_blacklist.zip'

dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')


def lambda_handler(event, context):
    usernames = []

    # Get all the users on the blacklist
    paginator = dynamodb.get_paginator('query')
    page_iterator = paginator.paginate(
        TableName=ROLE_TABLE_NAME,
        IndexName=ROLE_USERS_INDEX,
        KeyConditionExpression='role_users_pk = :blacklist',
        ExpressionAttributeValues={':blacklist': {'S': 'role_blacklist'}}
    )

    for page in page_iterator:
        usernames.extend(map(lambda item: '"{}"'.format(item['username']['S']), page['Items']))

    print("Found {} users in blocklist".format(len(usernames)))

    usernames_csv = bytes('username\n' + '\n'.join(usernames) + '\n', 'utf-8')

    # Compress it
    with zipfile.ZipFile('/tmp/autoblock_blacklist.zip', 'w') as usernames_zip:
        usernames_zip.writestr('usernames.csv', usernames_csv)

    # Upload it to S3
    s3.put_object(Bucket=OUTPUT_BUCKET_NAME, Key=BLACKLIST_KEY, Body=open('/tmp/autoblock_blacklist.zip', 'rb'))

    print("Successfully wrote to S3")
