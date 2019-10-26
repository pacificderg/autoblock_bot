from telethon import TelegramClient, events, sync
import requests, boto3, json, os


EXPECTED_CONFIG = ['bot_key', 'api_id', 'api_hash']


# Initialize parameters for use across invocations
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')
config = None
client = None


def load_config(ssm_parameter_path):
    params = ssm.get_parameters_by_path(Path=ssm_parameter_path)

    # /autoblock_bot/bot_key = SECRET_KEY => { 'bot_key': 'SECRET_KEY' }
    parsed_config = { item['Name'].split('/')[-1]: item['Value'] for item in params['Parameters'] }

    print("Loaded config", parsed_config)

    for key in EXPECTED_CONFIG:
        if not key in parsed_config:
            raise Exception("Expected key {} not found in config".format(key))

    global config
    config = parsed_config


def load_client():
    if config is None:
        print("Loading config and creating new app config")
        load_config(os.environ['APP_CONFIG_PATH'])

    global client
    client = TelegramClient('autoblock_bot', config['api_id'], config['api_hash'])
    client.start(bot_token=config['bot_key'])


def lambda_handler(event, context):
    if config is None:
        print("Loading config and creating new app config")
        load_config(os.environ['APP_CONFIG_PATH'])

    body = json.loads(event['body'])

    if 'message' in body:
        chat_id = body['message']['chat']['id']
        chat_type = body['message']['chat']['type']
        from_id = body['message']['from']['id']
        message_id = body['message']['message_id']

        if "new_chat_participant" in body['message']:
            user_id = body['message']['new_chat_participant']['id']
            username = body['message']['new_chat_participant']['username']
            
            handle_new_user(chat_id, user_id, username)
        elif chat_type == 'private' and 'text' in body['message'] and 'entities' in body['message']:
            text = body['message']['text']
            entities = body['message']['entities']

            handle_command(chat_id, from_id, message_id, text, entities)
    
    return {
        'statusCode': 200,
        'body': '{}'
    }


def handle_new_user(chat_id, user_id, username):
    if is_user_banned(user_id):
        # Ban user
        print('User {} (@{}) is in blocklist, banning'.format(user_id, username))
        payload = {
            'chat_id': chat_id,
            'user_id': user_id
        }

        requests.post('https://api.telegram.org/bot{}/kickChatMember'.format(config['bot_key']), data=payload)


def handle_command(chat_id, from_id, message_id, text, entities):
    print('Got command: {}'.format(text))

    # Check that the user who issued the command is an admin
    if not is_user_admin(from_id):
        print('Ignoring command from non-admin: {}'.format(from_id))
        return

    # Handle entities: if there are any bot commands, operate on the first one.
    command_entity = next(filter(lambda entity: entity['type'] == 'bot_command', entities), None)
    command = None

    if command_entity is not None:
        command = text[command_entity['offset']:command_entity['offset'] + command_entity['length']]

    print('Parsed command: {}'.format(command))

    # Unknown command, reply as such
    payload = {
        'chat_id': chat_id,
        'reply_to_message_id': message_id,
        'text': 'Unknown command'
    }
    requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)


def is_user_banned(user_id):
    response = dynamodb.get_item(
        TableName=os.environ['TABLE_NAME'],
        Key={'pk': {'S': 'user_{}'.format(user_id)}},
    )

    return 'Item' in response


def is_user_admin(user_id):
    response = dynamodb.get_item(
        TableName=os.environ['TABLE_NAME'],
        Key={'pk': {'S': 'admin_{}'.format(user_id)}},
    )

    return 'Item' in response
