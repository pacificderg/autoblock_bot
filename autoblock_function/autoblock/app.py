from . import blacklist, whitelist
from telethon import TelegramClient, sync
import boto3
import json
import os
import requests

# Constants we use in configuration below
EXPECTED_CONFIG = ['api_id', 'api_hash', 'root_users']
USERNAME_COMMANDS = ['/isbanned', '/add', '/remove']

# Collect environment settings
APP_CONFIG_PATH = os.environ.get('APP_CONFIG_PATH', '/autoblock_bot')
ROLE_TABLE_NAME = os.environ.get('ROLE_TABLE_NAME', 'Roles')
OUTPUT_BUCKET_NAME = os.environ.get('OUTPUT_BUCKET_NAME', 'output-bucket')

# Initialize parameters for use across invocations
cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
ssm = boto3.client('ssm')
config = None
clients = {}

handlers = {
    '/blacklist': blacklist.Handler(ROLE_TABLE_NAME, OUTPUT_BUCKET_NAME, 'blacklist', dynamodb, s3),
    '/whitelist': whitelist.Handler(ROLE_TABLE_NAME, 'whitelist', dynamodb)
}


def load_config():
    params = ssm.get_parameters_by_path(Path=APP_CONFIG_PATH)

    # /autoblock_bot/bot_key = SECRET_KEY => { 'bot_key': 'SECRET_KEY' }
    parsed_config = {
        item['Name'].split('/')[-1]: item['Value'].split(',') if item['Type'] == 'StringList'
        else item['Value'] for item in params['Parameters']
    }

    print("Loaded config", parsed_config)

    for key in EXPECTED_CONFIG:
        if key not in parsed_config:
            raise Exception("Expected key {} not found in config".format(key))

    global config
    config = parsed_config


def load_client(bot_key):
    if config is None:
        print("Loading config and creating new app config")
        load_config()

    bot_id = bot_key.split(':')[0]

    print('Starting client for bot', bot_id)

    global clients
    client = TelegramClient('/tmp/autoblock_bot_{}'.format(bot_id), config['api_id'], config['api_hash'])
    client.start(bot_token=bot_key)
    clients[bot_key] = client


def lambda_handler(event, context):
    if config is None:
        print("Loading config and creating new app config")
        load_config()

    handler = handlers[event['rawPath']]
    bot_key = event['queryStringParameters']['bot_key']
    body = json.loads(event['body'])

    if 'message' in body:
        chat_id = body['message']['chat']['id']
        chat_title = body['message']['chat'].get('title', 'Private chat')
        chat_type = body['message']['chat']['type']
        from_id = body['message']['from']['id']
        message_id = body['message']['message_id']

        if "new_chat_participant" in body['message']:
            user_id = body['message']['new_chat_participant']['id']
            username = body['message']['new_chat_participant'].get('username', 'no_username')

            handle_new_user(handler, bot_key, chat_id, chat_type, chat_title, user_id, username, message_id)
        elif chat_type == 'private' and 'text' in body['message'] and 'entities' in body['message']:
            text = body['message']['text']
            entities = body['message']['entities']

            handle_command(handler, bot_key, chat_id, from_id, message_id, text, entities)

    return {
        'statusCode': 200,
        'body': '{}'
    }


def handle_new_user(handler, bot_key, chat_id, chat_type, chat_title, user_id, username, message_id):
    bot_id = bot_key.split(':')[0]

    if str(user_id) == bot_id and chat_type == 'supergroup':
        print('Added to new chat: {} ({})'.format(chat_title, chat_id))
        payload = {
            'chat_id': chat_id,
            'text': 'Hello from the @FurryPartyOfArtAndLabor. In order for this bot to be operational in this chat, it'
                    ' must be made an admin.'
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()

        publish_count_metric('AddedToChat')
    elif not is_user_admin(user_id) and handler.is_user_banned(user_id):
        # Ban user
        print('User {} (@{}) is banned, banning'.format(user_id, username))
        payload = {
            'chat_id': chat_id,
            'user_id': user_id
        }

        response = requests.post('https://api.telegram.org/bot{}/kickChatMember'.format(bot_key), data=payload)

        if response.status_code == 200:
            publish_count_metric('UserRemoved')
        elif response.status_code == 400:
            payload = {
                'chat_id': chat_id,
                'reply_to_message_id': message_id,
                'text': 'Unable to remove @{} because this bot is not an admin'.format(username)
            }
            requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        else:
            response.raise_for_status()


def handle_command(handler, bot_key, chat_id, from_id, message_id, text, entities):
    print('Got command: {}'.format(text))

    # Handle entities: if there are any bot commands, operate on the first one.
    command_entity = next(filter(lambda entity: entity['type'] == 'bot_command', entities), None)

    if command_entity is None:
        # Ignore
        return

    command = text[command_entity['offset']:command_entity['offset'] + command_entity['length']]

    print('Parsed command: {}'.format(command))

    # Check for the start command first, and reply with a hello message
    if command == '/start':
        payload = {
            'chat_id': chat_id,
            'text': handler.welcome_message
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        publish_count_metric('StartCommand')
        return
    elif command == '/getlist':
        list_url = handler.get_blocklist_url()
        if list_url is None:
            payload = {
                'chat_id': chat_id,
                'reply_to_message_id': message_id,
                'text': 'No list is available.'
            }
            requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
            return

        print("Sending list: {}".format(list_url))
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'document': list_url
        }
        requests.post('https://api.telegram.org/bot{}/sendDocument'.format(bot_key), data=payload).raise_for_status()
        publish_count_metric('GetListCommand')
        return

    if command in USERNAME_COMMANDS:
        # Try to find a mention
        mention_entity = next(filter(lambda entity: entity['type'] == 'mention', entities), None)

        if mention_entity is None:
            # No username provided, reply with an error message
            payload = {
                'chat_id': chat_id,
                'reply_to_message_id': message_id,
                'text': 'This command requires a username.'
            }
            requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
            return

        username = text[mention_entity['offset']:mention_entity['offset'] + mention_entity['length']]

        if command == '/isbanned':
            handle_is_user_banned_command(handler, bot_key, chat_id, message_id, username)
        elif command == '/add':
            # Check that the user who issued the command is an admin
            if not is_user_admin(from_id):
                print('Ignoring command from non-admin: {}'.format(from_id))
                publish_count_metric('NonAdminCommandIgnored')
                return

            reason = text[mention_entity['offset'] + mention_entity['length']:].strip()
            handle_add_user_command(handler, bot_key, chat_id, message_id, username, reason)
        elif command == '/remove':
            # Check that the user who issued the command is an admin
            if not is_user_admin(from_id):
                print('Ignoring command from non-admin: {}'.format(from_id))
                publish_count_metric('NonAdminCommandIgnored')
                return

            handle_remove_user_command(handler, bot_key, chat_id, message_id, username)
    else:
        # Unknown command, reply as such
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': 'Unknown command'
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        publish_count_metric('UnknownCommand')


def handle_is_user_banned_command(handler, bot_key, chat_id, message_id, username):
    if clients.get(bot_key) is None:
        load_client(bot_key)

    try:
        info = clients[bot_key].get_entity(username)
    except ValueError as e:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': str(e)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        return

    reason = handler.is_user_banned(info.id)

    if reason:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': f'{username} ({info.id}) is banned: {reason}'
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
    else:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': '{} ({}) is not banned'.format(username, info.id)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()

    publish_count_metric('IsBannedCommand')


def handle_add_user_command(handler, bot_key, chat_id, message_id, username, reason):
    if clients.get(bot_key) is None:
        load_client(bot_key)

    try:
        info = clients[bot_key].get_entity(username)
    except ValueError as e:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': str(e)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        return

    # Check to see if user is already banned
    current_reason = handler.has_role(info.id)
    if current_reason:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': f'{username} ({info.id}) is already added: {current_reason}'
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        return

    handler.add_role_to(info.id, username, reason)

    # Send a confirmation back
    payload = {
        'chat_id': chat_id,
        'reply_to_message_id': message_id,
        'text': f'{username} ({info.id}) has been added: {reason if reason else "No reason given"}'
    }
    requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()

    publish_count_metric('AddUserCommand')


def handle_remove_user_command(handler, bot_key, chat_id, message_id, username):
    if clients.get(bot_key) is None:
        load_client(bot_key)

    try:
        info = clients[bot_key].get_entity(username)
    except ValueError as e:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': str(e)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        return

    # Check to see if user is not banned
    if not handler.has_role(info.id):
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': '{} ({}) is not added'.format(username, info.id)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()
        return

    handler.remove_role_from(info.id)

    # Send a confirmation back
    payload = {
        'chat_id': chat_id,
        'reply_to_message_id': message_id,
        'text': '{} ({}) has been removed'.format(username, info.id)
    }
    requests.post('https://api.telegram.org/bot{}/sendMessage'.format(bot_key), data=payload).raise_for_status()

    publish_count_metric('RemoveUserCommand')


def is_user_admin(user_id):
    if config is None:
        load_config()

    return str(user_id) in config['root_users']


def publish_count_metric(metric_name):
    cloudwatch.put_metric_data(
        Namespace='AutoblockBot',
        MetricData=[{
            'MetricName': metric_name,
            'Values': [1.0],
            'Unit': 'Count'
        }]
    )
