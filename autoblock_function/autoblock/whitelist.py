class Handler:
    def __init__(self, table_name, role_name, dynamodb):
        self.table_name = table_name
        self.role_name = role_name
        self.dynamodb = dynamodb

    def is_user_banned(self, user_id):
        return not self.has_role(user_id)

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
