from botocore.exceptions import ClientError
import logging

BLOCKLIST_KEY = 'autoblock_blacklist.zip'

class Handler:
    def __init__(self, table_name, output_bucket_name, role_name, dynamodb, s3):
        self.table_name = table_name
        self.output_bucket_name = output_bucket_name
        self.role_name = role_name
        self.dynamodb = dynamodb
        self.s3 = s3

    @property
    def welcome_message(self):
        return 'Hello from the @FurryPartyOfArtAndLabor. This bot was created and released to the public to help ' \
               'room owners secure their rooms from raids and alt-right recruiters. Simply add to your room and ' \
               'the bot will autoblock any Nazifur on its list of users from your room before any trouble can ' \
               'start.'

    def get_blocklist_url(self):
        try:
            response = self.s3.generate_presigned_url('get_object', Params={
                'Bucket': self.output_bucket_name,
                'Key': BLOCKLIST_KEY
            })
        except ClientError as e:
            logging.error(e)
            return None

        return response

    def is_user_banned(self, user_id):
        return self.has_role(user_id)

    def has_role(self, user_id):
        response = self.dynamodb.get_item(
            TableName=self.table_name,
            Key={
                'pk': {'S': 'user_{}'.format(user_id)},
                'sk': {'S': 'role_{}'.format(self.role_name)}
            }
        )

        return 'Item' in response

    def add_role_to(self, user_id, username):
        self.dynamodb.put_item(
            TableName=self.table_name,
            Item={
                'pk': {'S': 'user_{}'.format(user_id)},
                'sk': {'S': 'role_{}'.format(self.role_name)},
                'role_users_pk': {'S': 'role_{}'.format(self.role_name)},
                'role_users_sk': {'S': 'user_{}'.format(user_id)},
                'username': {'S': username}
            }
        )

    def remove_role_from(self, user_id):
        self.dynamodb.delete_item(
            TableName=self.table_name,
            Key={
                'pk': {'S': 'user_{}'.format(user_id)},
                'sk': {'S': 'role_{}'.format(self.role_name)}
            }
        )
