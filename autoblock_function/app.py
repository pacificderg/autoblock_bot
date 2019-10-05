import requests, boto3, json, os


# Initialize parameters for use across invocations
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')
config = None


def load_config(ssm_parameter_path):
    params = ssm.get_parameters_by_path(Path=ssm_parameter_path)

    # /autoblock_bot/bot_key = SECRET_KEY => { 'bot_key': 'SECRET_KEY' }
    global config
    config = { item['Name'].split('/')[-1]: item['Value'] for item in params['Parameters'] }

    print("Loaded config", config)


def lambda_handler(event, context):
    if config is None:
        print("Loading config and creating new app config")
        load_config(os.environ['APP_CONFIG_PATH'])

    body = json.loads(event['body'])

    if ("message" in body and "new_chat_participant" in body['message']):
        chat_id = body['message']['chat']['id']
        user_id = body['message']['new_chat_participant']['id']
        username = body['message']['new_chat_participant']['username']
        
        handle_new_user(chat_id, user_id, username)
    
    return {
        'statusCode': 200,
        'body': '{}'
    }


def handle_new_user(chat_id, user_id, username):
    query_response = dynamodb.query(
        TableName=os.environ['TABLE_NAME'],
        ExpressionAttributeValues={
            ':pk': {'S': 'user_{}'.format(user_id)}
        },
        KeyConditionExpression='pk = :pk'
    )
    
    if query_response['Count'] > 0:
        # Ban user
        print('User {} (@{}) is in blocklist, banning'.format(user_id, username))
        payload = {
            'chat_id': chat_id,
            'user_id': user_id
        }

        requests.post('https://api.telegram.org/bot{}/kickChatMember'.format(config['bot_key']), data=payload)
