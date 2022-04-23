from autoblock_function.autoblock import app
import requests, pytest, json, io


TEST_USER_ID = 99999999
BOT_USER_ID = 88888888
BOT_KEY = '88888888:TEST'


@pytest.fixture()
def message_event():
    return json.load(open('events/message.json'))


@pytest.fixture()
def new_member_event():
    return json.load(open('events/new_member.json'))


@pytest.fixture()
def new_member_whitelist_event():
    return json.load(open('events/new_member_whitelist.json'))


@pytest.fixture()
def unknown_command_event():
    return json.load(open('events/unknown_command.json'))


@pytest.fixture()
def is_banned_command_event():
    return json.load(open('events/isbanned_command.json'))


@pytest.fixture()
def remove_non_admin_command_event():
    return json.load(open('events/remove_non_admin_command.json'))


@pytest.fixture()
def public_command_event():
    return json.load(open('events/public_command.json'))


@pytest.fixture()
def add_command_event():
    return json.load(open('events/add_command.json'))


@pytest.fixture()
def add_whitelist_command_event():
    return json.load(open('events/add_whitelist_command.json'))


@pytest.fixture()
def remove_command_event():
    return json.load(open('events/remove_command.json'))


@pytest.fixture()
def remove_whitelist_command_event():
    return json.load(open('events/remove_whitelist_command.json'))


@pytest.fixture()
def start_command_event():
    return json.load(open('events/start_command.json'))


@pytest.fixture()
def bot_new_chat_event():
    return json.load(open('events/bot_new_chat.json'))
    

@pytest.fixture()
def ssm_configuration():
    return {
        'Parameters': [{
            'Name': '/autoblock_bot/bot_key',
            'Value': '88888888:TEST',
            'Type': 'String'
        }, {
            'Name': '/autoblock_bot/api_id',
            'Value': 'API_ID',
            'Type': 'String'
        }, {
            'Name': '/autoblock_bot/api_hash',
            'Value': 'API_HASH',
            'Type': 'String'
        }, {
            'Name': '/autoblock_bot/root_users',
            'Value': '{}'.format(TEST_USER_ID),
            'Type': 'StringList'
        }, {
            'Name': '/autoblock_bot/bot_userid',
            'Value': '{}'.format(BOT_USER_ID),
            'Type': 'String'
        }]
    }


@pytest.fixture()
def broken_ssm_configuration():
    return {
        'Parameters': []
    }

@pytest.fixture()
def added_user_response():
    return {
        'Item': {'pk': {'S': 'user_999999402'}, 'sk': {'S': 'role_blacklist'}, 'username': {'S': '@testuser'}},
    }


@pytest.fixture()
def added_user_whitelist_response():
    return {
        'Item': {'pk': {'S': 'user_999999402'}, 'sk': {'S': 'role_whitelist'}, 'username': {'S': '@testuser'}},
    }


@pytest.fixture()
def non_added_user_response():
    return {}


@pytest.fixture()
def mock_setup(ssm_configuration, mocker):
    mocker.patch('autoblock_function.autoblock.app.ssm.get_parameters_by_path')
    mocker.patch('autoblock_function.autoblock.app.dynamodb.get_item')
    mocker.patch('autoblock_function.autoblock.app.dynamodb.put_item')
    mocker.patch('autoblock_function.autoblock.app.dynamodb.delete_item')
    mocker.patch('autoblock_function.autoblock.app.cloudwatch.put_metric_data')
    mocker.patch('requests.post')
    mocker.patch('autoblock_function.autoblock.app.TelegramClient')

    app.ssm.get_parameters_by_path.return_value = ssm_configuration
    app.clients = {}


@pytest.fixture()
def mock_bad_setup(broken_ssm_configuration, mock_setup):
    app.ssm.get_parameters_by_path.return_value = broken_ssm_configuration


@pytest.fixture()
def telegram_test_user_entity(mocker):
    client_mock = mocker.Mock(spec=['start', 'get_entity'])
    client_mock.get_entity.return_value = mocker.Mock(id=TEST_USER_ID)
    return client_mock


def test_bad_ssm_config(message_event, mock_bad_setup):
    with pytest.raises(Exception):
        app.lambda_handler(message_event, "")

    assert app.config is None


def test_message_event(message_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(message_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    assert requests.post.call_count == 0


def test_start_command_event(start_command_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(start_command_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'text': 'Hello from the @FurryPartyOfArtAndLabor. This bot was created and released to the public to help'
                    ' room owners secure their rooms from raids and alt-right recruiters. Simply add to your room and'
                    ' the bot will autoblock any Nazifur on its list of users from your room before any trouble can'
                    ' start.'
        }
    )


def test_bot_new_chat_event(bot_new_chat_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(bot_new_chat_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': -1009999992388,
            'text': 'Hello from the @FurryPartyOfArtAndLabor. In order for this bot to be operational in this chat, it'
                    ' must be made an admin.'
        }
    )


def test_non_banned_user(new_member_event, non_added_user_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_added_user_response

    ret = app.lambda_handler(new_member_event, "")
    
    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 1
    assert requests.post.call_count == 0


def test_whitelisted_user(new_member_whitelist_event, added_user_whitelist_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = added_user_whitelist_response

    ret = app.lambda_handler(new_member_whitelist_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={
            'pk': {'S': 'user_999999402'},
            'sk': {'S': 'role_whitelist'}
        }
    )
    assert requests.post.call_count == 0


def test_blacklisted_user(new_member_event, added_user_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = added_user_response

    ret = app.lambda_handler(new_member_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={
            'pk': {'S': 'user_999999402'},
            'sk': {'S': 'role_blacklist'}
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/kickChatMember'.format(BOT_KEY),
        data={
            'chat_id': -1009999992388,
            'user_id': 999999402
        }
    )


def test_non_whitelisted_user(new_member_whitelist_event, non_added_user_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_added_user_response

    ret = app.lambda_handler(new_member_whitelist_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={
            'pk': {'S': 'user_999999402'},
            'sk': {'S': 'role_whitelist'}
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/kickChatMember'.format(BOT_KEY),
        data={
            'chat_id': -1009999992388,
            'user_id': 999999402
        }
    )


def test_unknown_command(unknown_command_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(unknown_command_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': 'Unknown command'
        }
    )


def test_command(
    is_banned_command_event,
    added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(is_banned_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_blacklist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': f'@test_user ({TEST_USER_ID}) is banned: No reason given'
        }
    )


def test_public_command(public_command_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(public_command_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    assert requests.post.call_count == 0


def test_command_from_non_admin(remove_non_admin_command_event, mock_setup):
    # pylint: disable=no-member

    ret = app.lambda_handler(remove_non_admin_command_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    assert requests.post.call_count == 0


def test_add_command(
    add_command_event,
    non_added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(add_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_blacklist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    app.dynamodb.put_item.assert_called_once_with(
        TableName='Roles',
        Item={
            'pk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'sk': {'S': 'role_blacklist'},
            'role_users_pk': {'S': 'role_blacklist'},
            'role_users_sk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'username': {'S': '@test_user'},
            'reason': {'S': 'test ban'}
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': f'@test_user ({TEST_USER_ID}) has been added: test ban'
        }
    )


def test_add_whitelist_command(
    add_whitelist_command_event,
    non_added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(add_whitelist_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_whitelist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    app.dynamodb.put_item.assert_called_once_with(
        TableName='Roles',
        Item={
            'pk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'sk': {'S': 'role_whitelist'},
            'role_users_pk': {'S': 'role_whitelist'},
            'role_users_sk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'username': {'S': '@test_user'},
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) has been added: No reason given'.format(TEST_USER_ID)
        }
    )


def test_add_command_added_user(
    add_command_event,
    added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(add_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_blacklist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    assert app.dynamodb.put_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) is already added: No reason given'.format(TEST_USER_ID)
        }
    )


def test_remove_command(
    remove_command_event,
    added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(remove_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_blacklist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    app.dynamodb.delete_item.assert_called_once_with(
        TableName='Roles',
        Key={
            'pk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'sk': {'S': 'role_blacklist'}
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) has been removed'.format(TEST_USER_ID)
        }
    )


def test_remove_whitelist_command(
    remove_whitelist_command_event,
    added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(remove_whitelist_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_whitelist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    app.dynamodb.delete_item.assert_called_once_with(
        TableName='Roles',
        Key={
            'pk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'sk': {'S': 'role_whitelist'}
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) has been removed'.format(TEST_USER_ID)
        }
    )


def test_remove_command_non_added_user(
    remove_command_event,
    non_added_user_response,
    telegram_test_user_entity,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_added_user_response
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(remove_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='Roles',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}, 'sk': {'S': 'role_blacklist'}}
    )
    app.clients[BOT_KEY].get_entity.assert_called_once_with('@test_user')
    assert app.dynamodb.delete_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/bot{}/sendMessage'.format(BOT_KEY),
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) is not added'.format(TEST_USER_ID)
        }
    )
