from . import blacklist, whitelist
from telethon import TelegramClient, sync
import boto3
import json
import os
import requests

# Constants we use in configuration below
EXPECTED_CONFIG = ['bot_key', 'api_id', 'api_hash', 'root_users']
USERNAME_COMMANDS = ['/isbanned', '/add', '/remove']

# Collect environment settings
APP_CONFIG_PATH = os.environ.get('APP_CONFIG_PATH', '/autoblock_bot')
ROLE_TABLE_NAME = os.environ.get('ROLE_TABLE_NAME', 'Roles')

# Initialize parameters for use across invocations
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')
config = None
client = None

handlers = {
    '/webhook/': blacklist.Handler(ROLE_TABLE_NAME, 'blacklist', dynamodb),
    '/blacklist/': blacklist.Handler(ROLE_TABLE_NAME, 'blacklist', dynamodb),
    '/whitelist/': whitelist.Handler(ROLE_TABLE_NAME, 'whitelist', dynamodb)
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


def load_client():
    if config is None:
        print("Loading config and creating new app config")
        load_config()

    global client
    client = TelegramClient('/tmp/autoblock_bot', config['api_id'], config['api_hash'])
    client.start(bot_token=config['bot_key'])


def lambda_handler(event, context):
    if config is None:
        print("Loading config and creating new app config")
        load_config()

    handler = handlers[event['path']]
    body = json.loads(event['body'])

    if 'message' in body:
        chat_id = body['message']['chat']['id']
        chat_type = body['message']['chat']['type']
        from_id = body['message']['from']['id']
        message_id = body['message']['message_id']

        if "new_chat_participant" in body['message']:
            user_id = body['message']['new_chat_participant']['id']
            username = body['message']['new_chat_participant']['username']

            handle_new_user(handler, chat_id, user_id, username)
        elif chat_type == 'private' and 'text' in body['message'] and 'entities' in body['message']:
            text = body['message']['text']
            entities = body['message']['entities']

            handle_command(handler, chat_id, from_id, message_id, text, entities)

    return {
        'statusCode': 200,
        'body': '{}'
    }


def handle_new_user(handler, chat_id, user_id, username):
    if not is_user_admin(user_id) and handler.is_user_banned(user_id):
        # Ban user
        print('User {} (@{}) is banned, banning'.format(user_id, username))
        payload = {
            'chat_id': chat_id,
            'user_id': user_id
        }

        requests.post('https://api.telegram.org/bot{}/kickChatMember'.format(config['bot_key']), data=payload)


def handle_command(handler, chat_id, from_id, message_id, text, entities):
    print('Got command: {}'.format(text))

    # Handle entities: if there are any bot commands, operate on the first one.
    command_entity = next(filter(lambda entity: entity['type'] == 'bot_command', entities), None)

    if command_entity is None:
        # Ignore
        return

    command = text[command_entity['offset']:command_entity['offset'] + command_entity['length']]

    print('Parsed command: {}'.format(command))

    # Check that the user who issued the command is an admin
    if not is_user_admin(from_id):
        print('Ignoring command from non-admin: {}'.format(from_id))
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
            requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
            return

        username = text[mention_entity['offset']:mention_entity['offset'] + mention_entity['length']]

        if command == '/isbanned':
            handle_is_user_banned_command(handler, chat_id, message_id, username)
        elif command == '/add':
            handle_add_user_command(handler, chat_id, message_id, username)
        elif command == '/remove':
            handle_remove_user_command(handler, chat_id, message_id, username)
    else:
        # Unknown command, reply as such
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': 'Unknown command'
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)


def handle_is_user_banned_command(handler, chat_id, message_id, username):
    if client is None:
        load_client()

    try:
        info = client.get_entity(username)
    except ValueError as e:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': str(e)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
        return

    if handler.is_user_banned(info.id):
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': '{} ({}) is banned'.format(username, info.id)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
    else:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': '{} ({}) is not banned'.format(username, info.id)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)


def handle_add_user_command(handler, chat_id, message_id, username):
    if client is None:
        load_client()

    try:
        info = client.get_entity(username)
    except ValueError as e:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': str(e)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
        return

    # Check to see if user is already banned
    if handler.has_role(info.id):
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': '{} ({}) is already added'.format(username, info.id)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
        return

    handler.add_role_to(info.id, username)

    # Send a confirmation back
    payload = {
        'chat_id': chat_id,
        'reply_to_message_id': message_id,
        'text': '{} ({}) has been added'.format(username, info.id)
    }
    requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)


def handle_remove_user_command(handler, chat_id, message_id, username):
    if client is None:
        load_client()

    try:
        info = client.get_entity(username)
    except ValueError as e:
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': str(e)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
        return

    # Check to see if user is not banned
    if not handler.has_role(info.id):
        payload = {
            'chat_id': chat_id,
            'reply_to_message_id': message_id,
            'text': '{} ({}) is not added'.format(username, info.id)
        }
        requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)
        return

    handler.remove_role_from(info.id)

    # Send a confirmation back
    payload = {
        'chat_id': chat_id,
        'reply_to_message_id': message_id,
        'text': '{} ({}) has been removed'.format(username, info.id)
    }
    requests.post('https://api.telegram.org/bot{}/sendMessage'.format(config['bot_key']), data=payload)


def is_user_admin(user_id):
    if config is None:
        load_config()

    return str(user_id) in config['root_users']
